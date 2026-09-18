"""Estágio 1 — pré-filtro léxico (GAP_BRIEF.md §5, estágio 1).

Um chunk passa se contiver **ambos**: ao menos um nome de pessoa (gazetteer ou
bigrama capitalizado desconhecido) e ao menos um gatilho relacional. Chunks com
gatilho de *depoimento* e um nome conhecido também passam (vão para a fila como
posição sobre a Escola do Recife, não como relação).

Ajustado para recall. A taxa de descarte por documento é registrada em
``prefiltro_stats.json`` para auditoria da agressividade do filtro.
"""
from __future__ import annotations

import datetime as _dt
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

# "SOBRENOME, Nome" (entrada de referência bibliográfica) e marcas típicas de lista de referências.
_RE_REF_AUTOR = re.compile(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}(?: [A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,})*, [A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+")
_RE_REF_MARCAS = re.compile(
    r"dispon[ií]vel em|acesso em|\bdoi\b|https?://|\bIn:|\(ed\.\)|\(org\.\)|\(coord\.\)|\bp\. \d+|\bv\. \d+|\bn\. \d+|"
    r"dissertação \(|tese \(|trabalho de conclusão|\[entrevista cedida",
    re.IGNORECASE,
)


def parece_bibliografia(texto: str) -> bool:
    """Lista de referências / notas bibliográficas: muitos nomes, nenhuma relação afirmada."""
    autores = len(_RE_REF_AUTOR.findall(texto or ""))
    marcas = len(_RE_REF_MARCAS.findall(texto or ""))
    return autores >= 3 or (autores >= 1 and marcas >= 3) or marcas >= 5

from ..config import Paths
from ..store import Dataset, read_json, read_jsonl, write_json, write_jsonl
from .lexicon import Gazetteer, Lexico, nomes_desconhecidos, normalizar


@dataclass
class Candidato:
    chunk_id: str
    pagina: int
    paragrafo: int
    texto: str
    contexto_anterior: str
    contexto_posterior: str
    nomes_conhecidos: list[dict[str, Any]] = field(default_factory=list)
    nomes_desconhecidos: list[str] = field(default_factory=list)
    gatilhos: list[dict[str, Any]] = field(default_factory=list)
    tipos_sugeridos: list[str] = field(default_factory=list)
    eh_depoimento: bool = False
    score: float = 0.0


def prefiltrar(
    chunks: list[dict[str, Any]],
    gazetteer: Gazetteer,
    lexico: Lexico,
    *,
    janela_contexto: int = 1,
) -> tuple[list[Candidato], dict[str, Any]]:
    candidatos: list[Candidato] = []
    n_nome_sem_gatilho = 0
    n_gatilho_sem_nome = 0
    n_bibliografia = 0
    freq_gatilhos: Counter[str] = Counter()
    freq_pessoas: Counter[str] = Counter()
    por_pagina: Counter[int] = Counter()

    for i, ch in enumerate(chunks):
        texto = ch["texto"]
        if parece_bibliografia(texto):
            n_bibliografia += 1
            continue
        norm = normalizar(texto)
        gat = lexico.gatilhos(norm)
        conhecidos = gazetteer.nomes(norm)
        desconhecidos = nomes_desconhecidos(texto, gazetteer)

        tem_nome = bool(conhecidos or desconhecidos)
        gat_relacionais = [g for g in gat if g.grupo != "depoimento"]
        dep = any(g.grupo == "depoimento" for g in gat)
        tem_gatilho = bool(gat_relacionais)

        if tem_nome and not tem_gatilho and not dep:
            n_nome_sem_gatilho += 1
        if tem_gatilho and not tem_nome:
            n_gatilho_sem_nome += 1

        passa = (tem_nome and tem_gatilho) or (dep and conhecidos)
        if not passa:
            continue

        for g in gat:
            freq_gatilhos[f"{g.grupo}:{g.termo}"] += 1
        for n in conhecidos:
            freq_pessoas[n.pessoa_id] += 1
        por_pagina[ch["pagina"]] += 1

        ant = " ".join(chunks[j]["texto"] for j in range(max(0, i - janela_contexto), i))
        pos = " ".join(chunks[j]["texto"] for j in range(i + 1, min(len(chunks), i + 1 + janela_contexto)))
        ids_conhecidos = {n.pessoa_id for n in conhecidos}
        score = 2.0 * len(ids_conhecidos) + 1.0 * len(desconhecidos) + 0.5 * len(gat_relacionais)
        if len(ids_conhecidos) >= 2:
            score += 2.0
        candidatos.append(
            Candidato(
                chunk_id=ch["chunk_id"],
                pagina=ch["pagina"],
                paragrafo=ch["paragrafo"],
                texto=texto,
                contexto_anterior=ant,
                contexto_posterior=pos,
                nomes_conhecidos=[asdict(n) for n in conhecidos],
                nomes_desconhecidos=desconhecidos,
                gatilhos=[asdict(g) for g in gat],
                tipos_sugeridos=sorted({g.tipo_sugerido for g in gat_relacionais if g.tipo_sugerido}),
                eh_depoimento=dep,
                score=round(score, 2),
            )
        )

    n = len(chunks)
    stats = {
        "n_chunks": n,
        "n_candidatos": len(candidatos),
        "taxa_descarte": round(1 - len(candidatos) / n, 4) if n else None,
        "n_com_nome_sem_gatilho": n_nome_sem_gatilho,
        "n_com_gatilho_sem_nome": n_gatilho_sem_nome,
        "n_bibliografia_descartados": n_bibliografia,
        "n_depoimentos_suspeitos": sum(1 for c in candidatos if c.eh_depoimento),
        "gatilhos_mais_frequentes": freq_gatilhos.most_common(25),
        "pessoas_mais_citadas": freq_pessoas.most_common(25),
        "candidatos_por_pagina": dict(sorted(por_pagina.items())),
        "gerado_em": _dt.datetime.now().isoformat(timespec="seconds"),
    }
    return candidatos, stats


def salvar_candidatos(paths: Paths, fonte_id: str, candidatos: list[Candidato], stats: dict[str, Any]) -> None:
    pasta = paths.work_fonte(fonte_id)
    pasta.mkdir(parents=True, exist_ok=True)
    write_jsonl(pasta / "candidatos.jsonl", (asdict(c) for c in candidatos))
    write_json(pasta / "prefiltro_stats.json", stats)


def carregar_candidatos(paths: Paths, fonte_id: str) -> list[dict[str, Any]]:
    return read_jsonl(paths.work_fonte(fonte_id) / "candidatos.jsonl")


def carregar_stats(paths: Paths, fonte_id: str) -> dict[str, Any] | None:
    p = paths.work_fonte(fonte_id) / "prefiltro_stats.json"
    return read_json(p) if p.exists() else None


def executar_prefiltro(paths: Paths, ds: Dataset, fonte_id: str) -> dict[str, Any]:
    chunks = read_jsonl(paths.work_fonte(fonte_id) / "chunks.jsonl")
    if not chunks:
        raise FileNotFoundError(f"Sem chunks para '{fonte_id}'. Rode `gap chunks {fonte_id}` primeiro.")
    gaz = Gazetteer.do_dataset(ds)
    lex = Lexico.carregar(paths.lexico)
    cands, stats = prefiltrar(chunks, gaz, lex)
    salvar_candidatos(paths, fonte_id, cands, stats)
    return stats
