"""Inventário de ``raw_pdfs/`` → esqueleto em ``fontes.jsonl`` (GAP_BRIEF.md §8).

Cada PDF ainda não referenciado vira uma fonte com ``processado: false`` e
``metadados_automaticos: true``. Autor/título/ano são inferidos do nome do
arquivo, dos metadados do PDF e das duas primeiras páginas — sempre para revisão.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

try:
    import pymupdf as fitz  # type: ignore
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

from ..config import Paths
from ..store import Dataset, slugify, write_jsonl
from .lexicon import normalizar

_ANO = re.compile(r"\b(19[2-9]\d|20[0-2]\d)\b")


def ler_metadados(pdf: Path, *, n_paginas_texto: int = 2, max_chars: int = 1500) -> dict[str, Any]:
    out: dict[str, Any] = {"paginas": None, "titulo_pdf": None, "autor_pdf": None, "texto_inicial": ""}
    try:
        doc = fitz.open(pdf)
    except Exception as exc:  # noqa: BLE001
        out["erro"] = f"{type(exc).__name__}: {exc}"
        return out
    try:
        out["paginas"] = doc.page_count
        md = doc.metadata or {}
        out["titulo_pdf"] = (md.get("title") or "").strip() or None
        out["autor_pdf"] = (md.get("author") or "").strip() or None
        partes = []
        for i in range(min(n_paginas_texto, doc.page_count)):
            partes.append(doc[i].get_text("text"))
        texto = re.sub(r"\s+", " ", " ".join(partes)).strip()
        out["texto_inicial"] = texto[:max_chars]
    finally:
        doc.close()
    return out


def inferir_tipo(nome_arquivo: str, texto: str) -> str:
    n = normalizar(nome_arquivo + " " + texto[:600])
    if "tcc" in n or "trabalho de conclusao" in n or "trabalho final de graduacao" in n:
        return "tcc"
    if "dissert" in n or "mestrado" in n:
        return "dissertacao"
    if re.search(r"\btese\b", n) or "doutorado" in n:
        return "tese"
    if "arquitextos" in n or "revista" in n or "vitruvius" in n or "artigo" in n:
        return "artigo"
    if "anais" in n or "seminario" in n or "docomomo" in n:
        return "anais"
    return "outro"


def inferir_ano(texto: str, nome_arquivo: str) -> int | None:
    anos = [int(a) for a in _ANO.findall(nome_arquivo)] + [int(a) for a in _ANO.findall(texto)]
    if not anos:
        return None
    # ano de defesa costuma ser o mais frequente/recente nas páginas de rosto
    cnt = Counter(anos)
    mais_freq = cnt.most_common()
    top = [a for a, c in mais_freq if c == mais_freq[0][1]]
    return max(top)


def inferir_autor(nome_arquivo: str, autor_pdf: str | None) -> str | None:
    stem = Path(nome_arquivo).stem
    m = re.match(r"^(?:DISSERTA[ÇC][ÃA]O|TESE|TCC)\s+(.+?)(?:\s*\(\d+\))?$", stem, re.IGNORECASE)
    if m:
        return m.group(1).replace("_", " ").strip()
    if autor_pdf and len(autor_pdf) > 3 and not re.search(r"@|\.com|user|admin|windows|microsoft", autor_pdf, re.I):
        return autor_pdf
    return None


def _sobrenome(autor: str | None) -> str | None:
    if not autor:
        return None
    partes = [p for p in re.split(r"[\s,]+", autor) if p]
    if not partes:
        return None
    if "," in autor:  # "AFONSO, Alcília"
        return partes[0]
    sufixos = {"filho", "neto", "junior", "júnior", "sobrinho"}
    for p in reversed(partes):
        if p.lower() not in sufixos and len(p) > 2:
            return p
    return partes[-1]


def propor_fonte(pdf: Path, ids_existentes: set[str]) -> dict[str, Any]:
    md = ler_metadados(pdf)
    texto = md.get("texto_inicial") or ""
    tipo = inferir_tipo(pdf.name, texto)
    ano = inferir_ano(texto, pdf.name)
    autor = inferir_autor(pdf.name, md.get("autor_pdf"))
    titulo = md.get("titulo_pdf") or pdf.stem.replace("_", " ").replace("+", " ").strip()
    sob = _sobrenome(autor)
    base = slugify(f"{sob}-{ano}" if sob and ano else (sob or pdf.stem))[:48] or "fonte"
    fid, n = base, 2
    while fid in ids_existentes:
        fid, n = f"{base}-{n}", n + 1
    ids_existentes.add(fid)
    notas = "Inventário automático — revisar autor, título, ano e tipo."
    if md.get("erro"):
        notas += f" Erro ao abrir PDF: {md['erro']}."
    if texto:
        notas += f" Início do texto: “{texto[:280]}…”"
    return {
        "id": fid,
        "tipo": tipo,
        "autor": autor,
        "titulo": titulo,
        "veiculo": None,
        "ano": ano,
        "url": None,
        "arquivo_local": f"raw_pdfs/{pdf.name}",
        "paginas": md.get("paginas"),
        "processado": False,
        "densidade": None,
        "prioridade": None,
        "notas": notas,
        "metadados_automaticos": True,
    }


def inventariar(paths: Paths, ds: Dataset, *, gravar: bool = True) -> list[dict[str, Any]]:
    if not paths.raw_pdfs.exists():
        return []
    referenciados = {normalizar(f.get("arquivo_local") or "") for f in ds.fontes}
    ids = {f["id"] for f in ds.fontes}
    novas: list[dict[str, Any]] = []
    for pdf in sorted(paths.raw_pdfs.glob("*.pdf"), key=lambda p: p.name.lower()):
        if normalizar(f"raw_pdfs/{pdf.name}") in referenciados:
            continue
        novas.append(propor_fonte(pdf, ids))
    if gravar and novas:
        write_jsonl(paths.fontes, ds.fontes + novas)
        ds.fontes.extend(novas)
    return novas


def fonte_para_pdf(paths: Paths, ds: Dataset, fonte_id: str) -> Path:
    f = ds.fontes_por_id.get(fonte_id)
    if not f:
        raise KeyError(f"Fonte '{fonte_id}' não existe em fontes.jsonl (rode `gap inventory`).")
    if not f.get("arquivo_local"):
        raise FileNotFoundError(f"Fonte '{fonte_id}' não tem arquivo_local (não está no corpus local).")
    p = paths.root / f["arquivo_local"]
    if not p.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {p}")
    return p


def registrar_pdf_avulso(paths: Paths, ds: Dataset, pdf: Path) -> dict[str, Any]:
    """Adiciona um PDF que não está em raw_pdfs/ (ou está, mas não foi inventariado)."""
    ids = {f["id"] for f in ds.fontes}
    fonte = propor_fonte(pdf, ids)
    try:
        rel = pdf.resolve().relative_to(paths.root.resolve())
        fonte["arquivo_local"] = str(rel).replace("\\", "/")
    except ValueError:
        fonte["arquivo_local"] = str(pdf.resolve())
    write_jsonl(paths.fontes, ds.fontes + [fonte])
    ds.fontes.append(fonte)
    return fonte
