"""Estado do pipeline por fonte (usado pela CLI ``gap status`` e pelo painel)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import Paths
from ..store import Dataset, read_json, read_jsonl


def _n_linhas(p: Path) -> int | None:
    if not p.exists():
        return None
    n = 0
    with p.open("rb") as fh:
        for line in fh:
            if line.strip():
                n += 1
    return n


def estado_fonte(paths: Paths, ds: Dataset, fonte: dict[str, Any]) -> dict[str, Any]:
    fid = fonte["id"]
    pasta = paths.work_fonte(fid)
    meta = read_json(pasta / "meta.json") if (pasta / "meta.json").exists() else None
    stats = read_json(pasta / "prefiltro_stats.json") if (pasta / "prefiltro_stats.json").exists() else None
    n_fila = _n_linhas(pasta / "fila.jsonl")
    extraidos = read_jsonl(pasta / "extraidos.jsonl") if (pasta / "extraidos.jsonl").exists() else None
    n_extraidos = sum(1 for r in extraidos if not r.get("erro")) if extraidos is not None else None
    n_erros_extracao = sum(1 for r in extraidos if r.get("erro")) if extraidos is not None else 0
    decisoes = read_jsonl(pasta / "decisoes.jsonl") if (pasta / "decisoes.jsonl").exists() else []
    decididos = {d.get("item_id") for d in decisoes if d.get("item_id")}
    pdf = paths.root / fonte["arquivo_local"] if fonte.get("arquivo_local") else None
    return {
        "id": fid,
        "titulo": fonte.get("titulo"),
        "autor": fonte.get("autor"),
        "ano": fonte.get("ano"),
        "tipo": fonte.get("tipo"),
        "densidade": fonte.get("densidade"),
        "prioridade": fonte.get("prioridade"),
        "processado": bool(fonte.get("processado")),
        "metadados_automaticos": bool(fonte.get("metadados_automaticos")),
        "tem_pdf": bool(pdf and pdf.exists()),
        "paginas": (meta or {}).get("n_paginas") or fonte.get("paginas"),
        "provavel_escaneado": (meta or {}).get("provavel_escaneado"),
        "n_chunks": (meta or {}).get("n_chunks") if meta else _n_linhas(pasta / "chunks.jsonl"),
        "n_candidatos": (stats or {}).get("n_candidatos") if stats else _n_linhas(pasta / "candidatos.jsonl"),
        "taxa_descarte": (stats or {}).get("taxa_descarte"),
        "n_extraidos": n_extraidos,
        "n_erros_extracao": n_erros_extracao,
        "n_fila": n_fila,
        "n_decisoes": len(decisoes) if (pasta / "decisoes.jsonl").exists() else None,
        "n_pendentes": (n_fila - len(decididos)) if n_fila is not None else None,
        "n_aceitos": sum(1 for d in decisoes if d.get("acao") == "aceitar"),
    }


def estado_fontes(paths: Paths, ds: Dataset) -> list[dict[str, Any]]:
    linhas = [estado_fonte(paths, ds, f) for f in ds.fontes]
    linhas.sort(key=lambda l: (l["prioridade"] is None, l["prioridade"] or 0, not l["tem_pdf"], l["id"]))
    return linhas
