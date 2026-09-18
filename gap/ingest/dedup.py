"""Estágio 4 — deduplicação, reforço e montagem da fila de triagem (GAP_BRIEF.md §5, estágios 3–4).

Se (origem, destino, tipo) já existe, não se cria linha nova: a fonte é anexada
a ``fontes[]`` da relação existente. Recorrência entre fontes independentes é
evidência mais forte e eleva o peso computado (§6.2).

A fila (``work/<fonte>/fila.jsonl``) reúne, por candidato extraído, a proposta
pré-preenchida, a resolução de entidades, o alerta de duplicidade e demais
alertas que a interface de triagem exibe.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

from ..config import TIPOS_DIRECIONAIS, TIPOS_RELACAO, Paths
from ..store import Dataset, read_jsonl, write_jsonl
from .extract import trecho_e_literal
from .resolve import Resolvedor


def chave_relacao(origem: str, destino: str, tipo: str, simetrico: bool) -> tuple[str, str, str]:
    if simetrico or tipo not in TIPOS_DIRECIONAIS:
        origem, destino = sorted((origem, destino))
    return (origem, destino, tipo)


def encontrar_duplicata(ds: Dataset, origem: str, destino: str, tipo: str, simetrico: bool) -> dict[str, Any] | None:
    alvo = chave_relacao(origem, destino, tipo, simetrico)
    for r in ds.relacoes:
        if chave_relacao(r["origem"], r["destino"], r["tipo"], bool(r.get("simetrico"))) == alvo:
            return r
    return None


def relacoes_do_par(ds: Dataset, a: str, b: str) -> list[dict[str, Any]]:
    par = tuple(sorted((a, b)))
    return [r for r in ds.relacoes if tuple(sorted((r["origem"], r["destino"]))) == par]


def fonte_ja_presente(rel: dict[str, Any], fonte_id: str) -> bool:
    return any(isinstance(f, dict) and f.get("fonte") == fonte_id for f in rel.get("fontes") or [])


def montar_fila(paths: Paths, ds: Dataset, fonte_id: str) -> dict[str, Any]:
    pasta = paths.work_fonte(fonte_id)
    extraidos = read_jsonl(pasta / "extraidos.jsonl")
    if not extraidos:
        raise FileNotFoundError(f"Sem extração para '{fonte_id}'. Rode `gap extract {fonte_id}` primeiro.")
    candidatos = {c["chunk_id"]: c for c in read_jsonl(pasta / "candidatos.jsonl")}
    res = Resolvedor(ds)
    itens: list[dict[str, Any]] = []
    n_dup = n_auto = n_humano = n_novo = 0

    for row in extraidos:
        cand = candidatos.get(row["candidato_id"], {})
        base = {
            "fonte": fonte_id,
            "candidato_id": row["candidato_id"],
            "pagina": row.get("pagina") or cand.get("pagina"),
            "texto": cand.get("texto"),
            "contexto_anterior": cand.get("contexto_anterior"),
            "contexto_posterior": cand.get("contexto_posterior"),
            "modelo": row.get("modelo"),
            "observacao": row.get("observacao"),
            "erro_extracao": row.get("erro"),
        }
        for i, r in enumerate(row.get("relacoes") or [], start=1):
            tipo = r.get("tipo") if r.get("tipo") in TIPOS_RELACAO else None
            ro = res.resolver(r.get("origem_nome") or "")
            rd = res.resolver(r.get("destino_nome") or "")
            alertas: list[dict[str, str]] = []
            for lado, rr in (("origem", ro), ("destino", rd)):
                if rr.decisao == "humano":
                    alertas.append({"tipo": "entidade", "texto": f"{lado.capitalize()} “{rr.nome}”: {rr.motivo}." + (f" Sugestão: {rr.candidatos[0]['nome']} ({rr.candidatos[0]['score']})." if rr.candidatos else "")})
                elif rr.decisao == "novo":
                    alertas.append({"tipo": "novo", "texto": f"{lado.capitalize()} “{rr.nome}” não existe na base. Id provisório sugerido: {rr.id_provisorio}."})
                elif rr.decisao == "auto" and rr.metodo == "fuzzy":
                    alertas.append({"tipo": "entidade", "texto": f"{lado.capitalize()} “{rr.nome}” casado automaticamente com {self_nome(ds, rr.id)} (similaridade {rr.score:.0f}). Confirme."})
            dup = None
            if ro.id and rd.id and tipo:
                if ro.id == rd.id:
                    alertas.append({"tipo": "fraco", "texto": "Origem e destino resolvem para a mesma pessoa."})
                d = encontrar_duplicata(ds, ro.id, rd.id, tipo, bool(r.get("simetrico")))
                if d:
                    mesma = fonte_ja_presente(d, fonte_id)
                    dup = {"relacao_id": d["id"], "mesma_fonte": mesma, "n_fontes": len({f.get('fonte') for f in d.get('fontes') or []})}
                    n_dup += 1
                    alertas.append({"tipo": "dup", "texto": (
                        f"Já existe {d['id']} ({tipo}) entre estas pessoas" + (", com esta mesma fonte. Aceitar apenas acrescenta a página/trecho." if mesma else ". Aceitar acrescenta esta fonte à relação existente e reforça o peso — não cria duplicata.")
                    )})
                outras = [x for x in relacoes_do_par(ds, ro.id, rd.id) if x["tipo"] != tipo]
                if outras:
                    alertas.append({"tipo": "info", "texto": "Outros vínculos já registrados para o par: " + ", ".join(f"{x['tipo']} ({x['id']})" for x in outras) + "."})
            if r.get("confianca_sugerida") == "hipotese":
                alertas.append({"tipo": "fraco", "texto": "O extrator classificou como hipótese: o trecho não afirma o vínculo diretamente."})
            if r.get("trecho") and cand.get("texto") and not trecho_e_literal(r.get("trecho"), cand.get("texto")):
                alertas.append({"tipo": "fraco", "texto": "O trecho citado não aparece literalmente no parágrafo-alvo — pode ter sido parafraseado; confira antes de aceitar."})
            if not tipo:
                alertas.append({"tipo": "fraco", "texto": f"Tipo inválido devolvido pelo extrator: {r.get('tipo')!r}."})
            for rr in (ro, rd):
                n_auto += rr.decisao == "auto"
                n_humano += rr.decisao == "humano"
                n_novo += rr.decisao == "novo"
            itens.append({
                **base,
                "id": f"{row['candidato_id']}-r{i}",
                "categoria": "relacao",
                "proposta": {
                    "origem_nome": r.get("origem_nome"), "destino_nome": r.get("destino_nome"),
                    "origem": ro.id, "destino": rd.id, "tipo": tipo, "subtipo": r.get("subtipo"),
                    "simetrico": bool(r.get("simetrico")), "periodo": r.get("periodo"), "descricao": r.get("descricao"),
                    "confianca": r.get("confianca_sugerida") or "documentado", "trecho": r.get("trecho"),
                    "justificativa": r.get("justificativa"), "pendencia": None,
                },
                "resolucao": {"origem": ro.as_dict(), "destino": rd.as_dict()},
                "duplicata": dup,
                "alertas": alertas,
            })
        for i, d in enumerate(row.get("depoimentos") or [], start=1):
            rp = res.resolver(d.get("pessoa_nome") or "")
            alertas = [{"tipo": "depoimento", "texto": "Posição sobre a existência da Escola do Recife: vai para depoimentos.jsonl, não gera aresta."}]
            if rp.decisao != "auto":
                alertas.append({"tipo": "entidade", "texto": f"Pessoa “{rp.nome}”: {rp.motivo}."})
            itens.append({
                **base,
                "id": f"{row['candidato_id']}-d{i}",
                "categoria": "depoimento",
                "proposta": {"pessoa_nome": d.get("pessoa_nome"), "pessoa": rp.id, "existe_escola": d.get("existe_escola"), "argumento": d.get("argumento"), "trecho": d.get("trecho")},
                "resolucao": {"pessoa": rp.as_dict()},
                "duplicata": None,
                "alertas": alertas,
            })

    # ordem: página, depois candidato — a triagem segue a leitura do texto
    itens.sort(key=lambda it: (it.get("pagina") or 0, it["candidato_id"], it["id"]))
    write_jsonl(pasta / "fila.jsonl", itens)
    stats = {
        "fonte": fonte_id,
        "n_itens": len(itens),
        "n_relacoes_propostas": sum(1 for it in itens if it["categoria"] == "relacao"),
        "n_depoimentos_propostos": sum(1 for it in itens if it["categoria"] == "depoimento"),
        "n_duplicatas": n_dup,
        "resolucao": {"auto": n_auto, "humano": n_humano, "novo": n_novo},
        "gerado_em": _dt.datetime.now().isoformat(timespec="seconds"),
    }
    return stats


def self_nome(ds: Dataset, pid: str | None) -> str:
    return ds.nome(pid) if pid else "?"


def carregar_fila(paths: Paths, fonte_id: str) -> list[dict[str, Any]]:
    return read_jsonl(paths.work_fonte(fonte_id) / "fila.jsonl")


def carregar_decisoes(paths: Paths, fonte_id: str) -> list[dict[str, Any]]:
    return read_jsonl(paths.work_fonte(fonte_id) / "decisoes.jsonl")
