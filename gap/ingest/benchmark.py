"""Benchmark do funil contra o gold standard (GAP_BRIEF.md §10, fase 2).

Duas medidas, independentes:

1. **Recall do pré-filtro** — para cada relação documentada do gold, localiza os
   chunks em que ambas as pessoas co-ocorrem (por nome/alias) e verifica se ao
   menos um sobreviveu ao pré-filtro. Não depende de LLM.
2. **Recall da extração** — se ``fila.jsonl`` existir, compara as propostas
   (par resolvido + tipo) com o gold. Também mede a taxa de falsos candidatos.

Metas (brief): recall ≥ 80% nas documentadas; ≤ 20% de falsos candidatos.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import TIPOS_DIRECIONAIS, Paths
from ..store import Dataset, read_jsonl
from .lexicon import Gazetteer, normalizar


def carregar_gold(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def _par(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((a, b)))  # type: ignore[return-value]


def recall_prefiltro(paths: Paths, ds: Dataset, fonte_id: str, gold: list[dict[str, Any]]) -> dict[str, Any]:
    pasta = paths.work_fonte(fonte_id)
    chunks = read_jsonl(pasta / "chunks.jsonl")
    cand_ids = {c["chunk_id"] for c in read_jsonl(pasta / "candidatos.jsonl")}
    gaz = Gazetteer.do_dataset(ds)
    ids_por_chunk = {c["chunk_id"]: gaz.ids(normalizar(c["texto"])) for c in chunks}

    # co-ocorrência com janela de 1 chunk (a frase pode citar A e o parágrafo anterior B)
    ordem = [c["chunk_id"] for c in chunks]
    vizinhos = {cid: set(ordem[max(0, i - 1): i + 2]) for i, cid in enumerate(ordem)}

    detalhes = []
    n_doc = n_loc = n_rec = 0
    for g in gold:
        if g.get("confianca") != "documentado":
            continue
        n_doc += 1
        a, b = g["origem"], g["destino"]
        chunks_par = [cid for cid, ids in ids_por_chunk.items() if a in ids and b in ids]
        chunks_janela = [
            cid for cid, ids in ids_por_chunk.items()
            if (a in ids or b in ids) and any((a in ids_por_chunk[v] and b in ids_por_chunk.get(v, set()) | ids) for v in vizinhos[cid])
        ]
        localizaveis = set(chunks_par) | set(chunks_janela)
        recuperados = localizaveis & cand_ids
        if localizaveis:
            n_loc += 1
        if recuperados:
            n_rec += 1
        detalhes.append({
            "origem": ds.nome(a), "destino": ds.nome(b), "tipo": g["tipo"],
            "localizavel": bool(localizaveis), "recuperado": bool(recuperados),
            "chunks": sorted(localizaveis)[:5],
        })
    return {
        "n_gold_documentadas": n_doc,
        "n_localizaveis": n_loc,
        "n_recuperadas": n_rec,
        "recall_sobre_localizaveis": round(n_rec / n_loc, 4) if n_loc else None,
        "recall_sobre_total": round(n_rec / n_doc, 4) if n_doc else None,
        "n_chunks": len(chunks),
        "n_candidatos": len(cand_ids),
        "taxa_descarte": round(1 - len(cand_ids) / len(chunks), 4) if chunks else None,
        "detalhes": detalhes,
    }


def recall_extracao(paths: Paths, ds: Dataset, fonte_id: str, gold: list[dict[str, Any]]) -> dict[str, Any] | None:
    fila = read_jsonl(paths.work_fonte(fonte_id) / "fila.jsonl")
    if not fila:
        return None
    gold_doc = [g for g in gold if g.get("confianca") == "documentado"]
    gold_chaves = {(_par(g["origem"], g["destino"]), g["tipo"]) for g in gold}
    gold_pares = {_par(g["origem"], g["destino"]) for g in gold}

    propostas = []
    for it in fila:
        if it.get("categoria") != "relacao":
            continue
        p = it["proposta"]
        ro, rd = it["resolucao"]["origem"], it["resolucao"]["destino"]
        o = p.get("origem") or (ro["candidatos"][0]["id"] if ro.get("candidatos") else None)
        d = p.get("destino") or (rd["candidatos"][0]["id"] if rd.get("candidatos") else None)
        if not (o and d and p.get("tipo")):
            propostas.append({"chave": None, "par": None})
            continue
        propostas.append({"chave": (_par(o, d), p["tipo"]), "par": _par(o, d)})

    encontradas_exato = {p["chave"] for p in propostas if p["chave"] in gold_chaves}
    encontradas_par = {p["par"] for p in propostas if p["par"] in gold_pares}
    n_doc = len(gold_doc)
    rec_exato = sum(1 for g in gold_doc if (_par(g["origem"], g["destino"]), g["tipo"]) in encontradas_exato)
    rec_par = sum(1 for g in gold_doc if _par(g["origem"], g["destino"]) in encontradas_par)
    falsos = sum(1 for p in propostas if p["par"] is None or p["par"] not in gold_pares)
    return {
        "n_propostas": len(propostas),
        "n_gold_documentadas": n_doc,
        "recall_par_e_tipo": round(rec_exato / n_doc, 4) if n_doc else None,
        "recall_par": round(rec_par / n_doc, 4) if n_doc else None,
        "n_falsos_candidatos": falsos,
        "taxa_falsos": round(falsos / len(propostas), 4) if propostas else None,
        "meta_recall_atingida": (rec_exato / n_doc >= 0.8) if n_doc else None,
        "meta_falsos_atingida": (falsos / len(propostas) <= 0.2) if propostas else None,
        "nao_recuperadas": [
            {"origem": ds.nome(g["origem"]), "destino": ds.nome(g["destino"]), "tipo": g["tipo"]}
            for g in gold_doc if (_par(g["origem"], g["destino"]), g["tipo"]) not in encontradas_exato
        ],
    }


def executar_benchmark(paths: Paths, ds: Dataset, fonte_id: str, gold_path: Path | None = None) -> dict[str, Any]:
    gold_path = gold_path or (paths.tests / "gold" / fonte_id / "relacoes_gold.jsonl")
    if not gold_path.exists():
        raise FileNotFoundError(f"Gold standard não encontrado: {gold_path}")
    gold = carregar_gold(gold_path)
    return {
        "fonte": fonte_id,
        "gold": str(gold_path),
        "n_gold": len(gold),
        "prefiltro": recall_prefiltro(paths, ds, fonte_id, gold),
        "extracao": recall_extracao(paths, ds, fonte_id, gold),
    }
