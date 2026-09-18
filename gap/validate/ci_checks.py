"""Regras de validação executadas em CI a cada PR (GAP_BRIEF.md §3.5).

Cada regra devolve ``Problema`` com nível ``erro`` (bloqueia o merge) ou
``aviso`` (aparece no relatório, não bloqueia).
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from ..config import Paths, TIPOS_DIRECIONAIS
from ..store import Dataset, load_dataset
from .schema import Depoimento, Fonte, Pessoa, Relacao

PERIODO_RE = re.compile(
    r"^(?:(?:c\.|ca\.)\s*)?(?:\d{4}(?:-(?:\d{4})?)?|-\d{4}|anos \d{4}|d[ée]cada de \d{4})$"
)


@dataclass
class Problema:
    nivel: str  # "erro" | "aviso"
    regra: str
    entidade: str
    mensagem: str

    def __str__(self) -> str:
        return f"[{self.nivel.upper():5}] {self.regra:<22} {self.entidade:<28} {self.mensagem}"


def _fmt_validation_error(exc: ValidationError) -> str:
    partes = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e.get("loc", ()))
        partes.append(f"{loc}: {e.get('msg')}")
    return "; ".join(partes)


def _par(rel: dict[str, Any]) -> tuple[str, str, str]:
    """Chave de duplicidade (origem, destino, tipo).

    Para relações simétricas a ordem do par não importa.
    """
    o, d, t = rel.get("origem", ""), rel.get("destino", ""), rel.get("tipo", "")
    if rel.get("simetrico") or t not in TIPOS_DIRECIONAIS:
        o, d = sorted((o, d))
    return (o, d, t)


def validar(ds: Dataset, paths: Paths | None = None) -> list[Problema]:
    problemas: list[Problema] = []
    err = lambda regra, ent, msg: problemas.append(Problema("erro", regra, ent, msg))  # noqa: E731
    warn = lambda regra, ent, msg: problemas.append(Problema("aviso", regra, ent, msg))  # noqa: E731

    # ------------------------------------------------------------------ 1. esquema
    for nome, rows, modelo in (
        ("pessoas", ds.pessoas, Pessoa),
        ("relacoes", ds.relacoes, Relacao),
        ("depoimentos", ds.depoimentos, Depoimento),
        ("fontes", ds.fontes, Fonte),
    ):
        for i, row in enumerate(rows, start=1):
            ent = f"{nome}:{row.get('id', f'linha {i}')}"
            try:
                modelo.model_validate(row)
            except ValidationError as exc:
                err("schema", ent, _fmt_validation_error(exc))

    # ------------------------------------------------------------------ 2. ids únicos
    for nome, rows in (("pessoas", ds.pessoas), ("relacoes", ds.relacoes),
                       ("depoimentos", ds.depoimentos), ("fontes", ds.fontes)):
        cnt = Counter(r.get("id") for r in rows)
        for k, n in cnt.items():
            if k and n > 1:
                err("id-duplicado", f"{nome}:{k}", f"id aparece {n} vezes")

    pessoas_ids = {p.get("id") for p in ds.pessoas}
    fontes_ids = {f.get("id") for f in ds.fontes}
    inst_ids = {i.get("id") for i in ds.instituicoes}
    rel_ids = {r.get("id") for r in ds.relacoes}

    # ------------------------------------------------------------------ 3. integridade referencial
    for r in ds.relacoes:
        ent = f"relacoes:{r.get('id')}"
        for campo in ("origem", "destino"):
            if r.get(campo) not in pessoas_ids:
                err("referencia", ent, f"{campo} '{r.get(campo)}' não existe em pessoas.jsonl")
        for f in r.get("fontes") or []:
            if isinstance(f, dict) and f.get("fonte") not in fontes_ids:
                err("referencia", ent, f"fonte '{f.get('fonte')}' não existe em fontes.jsonl")
        if r.get("rompe") and r.get("rompe") not in rel_ids:
            err("referencia", ent, f"rompe '{r.get('rompe')}' não existe em relacoes.jsonl")
    for d in ds.depoimentos:
        ent = f"depoimentos:{d.get('id')}"
        if d.get("pessoa") not in pessoas_ids:
            err("referencia", ent, f"pessoa '{d.get('pessoa')}' não existe em pessoas.jsonl")
        f = d.get("fonte") or {}
        if isinstance(f, dict) and f.get("fonte") not in fontes_ids:
            err("referencia", ent, f"fonte '{f.get('fonte')}' não existe em fontes.jsonl")
    for p in ds.pessoas:
        ent = f"pessoas:{p.get('id')}"
        for fid in p.get("fontes") or []:
            if fid not in fontes_ids:
                err("referencia", ent, f"fonte '{fid}' não existe em fontes.jsonl")
        # ---------------------------------------------------------- 5. vocabulário de instituições
        for a in p.get("atuacao") or []:
            if isinstance(a, dict) and a.get("nome") not in inst_ids:
                err("instituicao", ent, f"atuacao.nome '{a.get('nome')}' não está em instituicoes.yaml")
        for fm in p.get("formacao") or []:
            if isinstance(fm, dict) and fm.get("instituicao") not in inst_ids:
                err("instituicao", ent, f"formacao.instituicao '{fm.get('instituicao')}' não está em instituicoes.yaml")
        # ---------------------------------------------------------- 6. qualidade do nome
        nome = (p.get("nome") or "").strip()
        if nome and len(nome.split()) == 1:
            warn("nome-incompleto", ent, f"nome com um único token: '{nome}' — confirmar em outra fonte")
        if p.get("atribuicao") is None:
            warn("atribuicao-ausente", ent, "atribuicao não definida (arquiteto | urbanista | engenheiro | professor | outro)")
        if p.get("status") == "verificado" and not p.get("fontes"):
            warn("sem-fonte", ent, "pessoa verificada sem nenhuma fonte listada")

    # ------------------------------------------------------------------ 7–9. evidência e duplicidade
    chaves: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for r in ds.relacoes:
        ent = f"relacoes:{r.get('id')}"
        fontes = [f for f in (r.get("fontes") or []) if isinstance(f, dict)]
        conf = r.get("confianca")
        if conf == "documentado" and not fontes:
            err("evidencia", ent, "confianca=documentado exige ao menos uma fonte")
        if conf == "hipotese" and not fontes and not (r.get("pendencia") or "").strip():
            err("evidencia", ent, "hipótese sem fonte exige pendencia não vazia")
        if r.get("simetrico") and r.get("tipo") in TIPOS_DIRECIONAIS:
            warn("direcao", ent, f"tipo '{r.get('tipo')}' é direcional; simetrico=true é suspeito")
        per = r.get("periodo")
        if per and not PERIODO_RE.match(str(per)):
            warn("periodo", ent, f"periodo '{per}' fora do formato AAAA, AAAA-AAAA, AAAA- ou -AAAA")
        for f in fontes:
            if f.get("trecho") and len(f["trecho"]) > 400:
                warn("trecho-longo", ent, "trecho com mais de 400 caracteres — manter apenas a frase que fundamenta (direitos autorais)")
        chaves[_par(r)].append(r.get("id", "?"))
    for chave, ids in chaves.items():
        if len(ids) > 1:
            err("duplicata", f"relacoes:{','.join(ids)}",
                f"mesmo par e tipo {chave} em {len(ids)} linhas — mesclar fontes em uma só")

    # ------------------------------------------------------------------ 10. aliases
    variante_para: dict[str, set[str]] = defaultdict(set)
    for pid, variantes in ds.aliases.items():
        if pid not in pessoas_ids:
            err("alias", f"aliases:{pid}", "id canônico não existe em pessoas.jsonl")
        for v in variantes or []:
            variante_para[str(v).strip().lower()].add(pid)
    for v, ids in variante_para.items():
        if len(ids) > 1:
            warn("alias-ambiguo", f"aliases:'{v}'", f"variante mapeada para {sorted(ids)} — resolução exigirá fila humana")

    # ------------------------------------------------------------------ 11. arquivos locais das fontes
    if paths is not None and paths.raw_pdfs.exists():
        for f in ds.fontes:
            arq = f.get("arquivo_local")
            if arq:
                p = paths.root / arq
                if not p.exists():
                    warn("arquivo-ausente", f"fontes:{f.get('id')}", f"arquivo_local não encontrado: {arq}")

    return problemas


def validar_repositorio(paths: Paths | None = None) -> list[Problema]:
    paths = paths or Paths()
    return validar(load_dataset(paths), paths)


def resumo(problemas: list[Problema]) -> tuple[int, int]:
    erros = sum(1 for p in problemas if p.nivel == "erro")
    avisos = sum(1 for p in problemas if p.nivel == "aviso")
    return erros, avisos
