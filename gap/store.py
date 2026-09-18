"""Leitura e escrita dos arquivos-fonte (JSONL e YAML) e carga do conjunto de dados.

Regras:
- JSONL: um registro por linha, UTF-8, ``ensure_ascii=False`` para manter acentos
  legíveis no diff do Git.
- Nunca reordenar linhas existentes ao acrescentar (diff mínimo).
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from .config import Paths


# --------------------------------------------------------------------------- #
# Primitivas
# --------------------------------------------------------------------------- #

def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Lê um JSONL. Arquivo ausente → lista vazia. Linhas em branco são ignoradas."""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for n, line in enumerate(fh, start=1):
            s = line.strip()
            if not s:
                continue
            try:
                rows.append(json.loads(s))
            except json.JSONDecodeError as exc:  # pragma: no cover - mensagem útil
                raise ValueError(f"{path.name}:{n}: JSON inválido — {exc}") from exc
    return rows


def dumps(row: dict[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=False, separators=(",", ":"))


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(dumps(row) + "\n")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_newline = path.exists() and path.stat().st_size > 0
    if needs_newline:
        with path.open("rb") as fh:
            fh.seek(-1, 2)
            needs_newline = fh.read(1) != b"\n"
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        if needs_newline:
            fh.write("\n")
        fh.write(dumps(row) + "\n")


def read_yaml(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def write_yaml(path: Path, data: Any, header: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        if header:
            for line in header.rstrip("\n").splitlines():
                fh.write(f"# {line}\n" if line.strip() else "#\n")
            fh.write("\n")
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False, default_flow_style=None, width=100)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: Any, indent: int | None = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=indent)
        fh.write("\n")


def hoje() -> str:
    return _dt.date.today().isoformat()


_SLUG_MAP = str.maketrans(
    "áàâãäéèêëíìîïóòôõöúùûüçñÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ",
    "aaaaaeeeeiiiiooooouuuucnAAAAAEEEEIIIIOOOOOUUUUCN",
)


def slugify(texto: str) -> str:
    """Converte "Maurício do Passo Castro" → "mauricio-do-passo-castro"."""
    s = texto.translate(_SLUG_MAP).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def proximo_id(prefixo: str, existentes: Iterable[str], largura: int = 4) -> str:
    """Gera "rel-0033" a partir dos ids existentes com o mesmo prefixo."""
    maior = 0
    padrao = re.compile(rf"^{re.escape(prefixo)}-(\d+)$")
    for e in existentes:
        m = padrao.match(e or "")
        if m:
            maior = max(maior, int(m.group(1)))
    return f"{prefixo}-{maior + 1:0{largura}d}"


# --------------------------------------------------------------------------- #
# Conjunto de dados
# --------------------------------------------------------------------------- #

@dataclass
class Dataset:
    """Conteúdo bruto (dicts) de todos os arquivos versionados."""

    pessoas: list[dict[str, Any]] = field(default_factory=list)
    relacoes: list[dict[str, Any]] = field(default_factory=list)
    depoimentos: list[dict[str, Any]] = field(default_factory=list)
    fontes: list[dict[str, Any]] = field(default_factory=list)
    instituicoes: list[dict[str, Any]] = field(default_factory=list)
    aliases: dict[str, list[str]] = field(default_factory=dict)

    # índices
    @property
    def pessoas_por_id(self) -> dict[str, dict[str, Any]]:
        return {p["id"]: p for p in self.pessoas if "id" in p}

    @property
    def relacoes_por_id(self) -> dict[str, dict[str, Any]]:
        return {r["id"]: r for r in self.relacoes if "id" in r}

    @property
    def fontes_por_id(self) -> dict[str, dict[str, Any]]:
        return {f["id"]: f for f in self.fontes if "id" in f}

    @property
    def instituicoes_por_id(self) -> dict[str, dict[str, Any]]:
        return {i["id"]: i for i in self.instituicoes if "id" in i}

    def nome(self, pessoa_id: str) -> str:
        p = self.pessoas_por_id.get(pessoa_id)
        return p["nome"] if p else pessoa_id

    def aliases_de(self, pessoa_id: str) -> list[str]:
        return list(self.aliases.get(pessoa_id, []))


def load_dataset(paths: Paths | None = None) -> Dataset:
    paths = paths or Paths()
    inst = read_yaml(paths.instituicoes) or []
    aliases = read_yaml(paths.aliases) or {}
    return Dataset(
        pessoas=read_jsonl(paths.pessoas),
        relacoes=read_jsonl(paths.relacoes),
        depoimentos=read_jsonl(paths.depoimentos),
        fontes=read_jsonl(paths.fontes),
        instituicoes=list(inst),
        aliases={k: list(v or []) for k, v in dict(aliases).items()},
    )


ALIASES_HEADER = """Variantes de nome → id canônico em pessoas.jsonl.

Chave: id da pessoa. Valor: lista de variantes textuais encontradas nas fontes.
O sistema aprende: quando a triagem confirma uma variante, ela é acrescentada aqui.
Variantes de um único token (ex.: "Russo") são usadas pelo pré-filtro e pela
resolução de entidades, mas NUNCA resolvem automaticamente — sempre passam
pela fila humana (GAP_BRIEF §5, estágio 3)."""


def salvar_aliases(paths: Paths, aliases: dict[str, list[str]]) -> None:
    ordenado = {k: sorted(set(v), key=str.lower) for k, v in aliases.items()}
    write_yaml(paths.aliases, ordenado, header=ALIASES_HEADER)
