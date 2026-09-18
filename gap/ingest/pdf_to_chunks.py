"""Estágio 0 — PDF → texto com posição (GAP_BRIEF.md §5, estágio 0).

Saída: ``work/<fonte-id>/chunks.jsonl`` com ``{chunk_id, pagina, paragrafo, texto}``
e ``work/<fonte-id>/meta.json``. Chunk = parágrafo (bloco de texto do PDF),
não janela fixa de tokens: relações vivem em frases isoladas e a proveniência
por página é exigência do esquema.
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:  # pymupdf ≥ 1.24 expõe o nome novo; `fitz` continua válido
    import pymupdf as fitz  # type: ignore
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

from ..config import Paths
from ..store import read_json, read_jsonl, write_json, write_jsonl


@dataclass
class Chunk:
    chunk_id: str
    pagina: int
    paragrafo: int
    texto: str
    n_chars: int


_HIFEN_QUEBRA = re.compile(r"(\w)-\s*\n\s*(\w)")
_ESPACOS = re.compile(r"[ \t ]+")
_SO_NUMEROS = re.compile(r"^[\d\s\-–—|.·]+$")
_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f�]")
_TERMINAL = ".!?:;\"”’)»]"


def limpar_texto(t: str) -> str:
    t = _CONTROLE.sub("", t)
    t = _HIFEN_QUEBRA.sub(r"\1\2", t)  # "arquite-\ntura" → "arquitetura"
    t = t.replace("\r", "\n")
    t = re.sub(r"\s*\n\s*", " ", t)
    t = _ESPACOS.sub(" ", t).strip()
    return t


def _parece_ruido(texto: str) -> bool:
    if _SO_NUMEROS.match(texto):
        return True
    # cabeçalhos/rodapés curtos em caixa alta, numeração de página, URLs soltas
    if len(texto) < 60 and (texto.isupper() or re.match(r"^(p\.|pág\.|página)\s*\d+", texto, re.I)):
        return True
    if re.match(r"^https?://\S+$", texto):
        return True
    return False


def _deve_mesclar(anterior: str, proximo: str) -> bool:
    """Blocos que o PDF quebrou no meio de um parágrafo (colunas, imagens)."""
    if not anterior or not proximo:
        return False
    if anterior[-1] in _TERMINAL:
        return False
    return proximo[0].islower() or proximo[0] in ",;)"


def extrair_chunks(pdf_path: Path, fonte_id: str, *, min_chars: int = 40) -> tuple[list[Chunk], dict[str, Any]]:
    doc = fitz.open(pdf_path)
    chunks: list[Chunk] = []
    total_chars = 0
    paginas_vazias = 0
    try:
        for pno, page in enumerate(doc, start=1):
            blocos = page.get_text("blocks")
            blocos = sorted((b for b in blocos if len(b) >= 7 and b[6] == 0), key=lambda b: (round(b[1], 1), round(b[0], 1)))
            textos: list[str] = []
            for b in blocos:
                t = limpar_texto(b[4])
                if not t:
                    continue
                if textos and _deve_mesclar(textos[-1], t):
                    textos[-1] = f"{textos[-1]} {t}"
                else:
                    textos.append(t)
            pagina_chars = 0
            idx = 0
            for t in textos:
                pagina_chars += len(t)
                if len(t) < min_chars or _parece_ruido(t):
                    continue
                idx += 1
                chunks.append(Chunk(f"{fonte_id}-p{pno:04d}-b{idx:03d}", pno, idx, t, len(t)))
            total_chars += pagina_chars
            if pagina_chars < 20:
                paginas_vazias += 1
        n_paginas = doc.page_count
    finally:
        doc.close()

    media = total_chars / n_paginas if n_paginas else 0
    meta = {
        "fonte_id": fonte_id,
        "arquivo": str(pdf_path),
        "n_paginas": n_paginas,
        "n_chunks": len(chunks),
        "n_chars": total_chars,
        "chars_por_pagina": round(media, 1),
        "paginas_sem_texto": paginas_vazias,
        "provavel_escaneado": media < 200,
        "gerado_em": _dt.datetime.now().isoformat(timespec="seconds"),
    }
    return chunks, meta


def salvar_chunks(paths: Paths, fonte_id: str, chunks: list[Chunk], meta: dict[str, Any]) -> Path:
    pasta = paths.work_fonte(fonte_id)
    pasta.mkdir(parents=True, exist_ok=True)
    write_jsonl(pasta / "chunks.jsonl", (asdict(c) for c in chunks))
    write_json(pasta / "meta.json", meta)
    return pasta / "chunks.jsonl"


def carregar_chunks(paths: Paths, fonte_id: str) -> list[dict[str, Any]]:
    return read_jsonl(paths.work_fonte(fonte_id) / "chunks.jsonl")


def carregar_meta(paths: Paths, fonte_id: str) -> dict[str, Any] | None:
    p = paths.work_fonte(fonte_id) / "meta.json"
    return read_json(p) if p.exists() else None


def processar_pdf(paths: Paths, fonte_id: str, pdf_path: Path, *, min_chars: int = 40) -> dict[str, Any]:
    chunks, meta = extrair_chunks(pdf_path, fonte_id, min_chars=min_chars)
    salvar_chunks(paths, fonte_id, chunks, meta)
    return meta
