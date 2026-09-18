"""Caminhos, enumerações e constantes compartilhadas.

Tudo que é "decisão de projeto" e aparece em mais de um módulo vive aqui,
para que exista um único lugar a alterar (GAP_BRIEF.md §2, §3).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


# --------------------------------------------------------------------------- #
# Caminhos
# --------------------------------------------------------------------------- #

def _default_root() -> Path:
    env = os.environ.get("GAP_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Paths:
    """Todos os caminhos do repositório derivados de uma raiz.

    Permite apontar testes para diretórios temporários e manter o restante do
    código livre de caminhos absolutos (Windows-safe via ``pathlib``).
    """

    root: Path = field(default_factory=_default_root)

    # dados versionados
    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def vocab(self) -> Path:
        return self.data / "vocabularios"

    @property
    def pessoas(self) -> Path:
        return self.data / "pessoas.jsonl"

    @property
    def relacoes(self) -> Path:
        return self.data / "relacoes.jsonl"

    @property
    def depoimentos(self) -> Path:
        return self.data / "depoimentos.jsonl"

    @property
    def fontes(self) -> Path:
        return self.data / "fontes.jsonl"

    @property
    def instituicoes(self) -> Path:
        return self.vocab / "instituicoes.yaml"

    @property
    def aliases(self) -> Path:
        return self.vocab / "aliases.yaml"

    @property
    def lexico(self) -> Path:
        return self.vocab / "lexico_relacional.yaml"

    # não versionados
    @property
    def raw_pdfs(self) -> Path:
        env = os.environ.get("GAP_RAW_PDFS")
        return Path(env).resolve() if env else self.root / "raw_pdfs"

    @property
    def work(self) -> Path:
        return self.root / "work"

    @property
    def export(self) -> Path:
        return self.root / "export"

    @property
    def site(self) -> Path:
        return self.root / "site"

    @property
    def site_data(self) -> Path:
        return self.site / "data"

    @property
    def tests(self) -> Path:
        return self.root / "tests"

    # versionado: propostas de extração pré-triagem (só trechos curtos), por fonte
    @property
    def extracoes(self) -> Path:
        return self.root / "extracoes"

    def extracao_fonte(self, fonte_id: str) -> Path:
        return self.extracoes / fonte_id / "extraidos.jsonl"

    def work_fonte(self, fonte_id: str) -> Path:
        return self.work / fonte_id


# --------------------------------------------------------------------------- #
# Enumerações (GAP_BRIEF.md §3)
# --------------------------------------------------------------------------- #

TIPOS_RELACAO: tuple[str, ...] = (
    "heranca",
    "mestre-aprendiz",
    "estudo",
    "trabalho",
    "societario",
    "dissidencia",
    "coautoria-pontual",
)

# Tipos cuja direção origem → destino carrega significado próprio.
# `heranca` pode ser simétrica (primos) ou não (filho de); fica fora da lista.
TIPOS_DIRECIONAIS: frozenset[str] = frozenset({"mestre-aprendiz", "estudo", "dissidencia"})

# Tipos que representam transmissão/ensino (critério de proselitismo, Zein 5).
TIPOS_ENSINO: frozenset[str] = frozenset({"mestre-aprendiz", "estudo"})

CONFIANCAS: tuple[str, ...] = ("documentado", "tradicao_oral", "hipotese")
STATUS: tuple[str, ...] = ("rascunho", "verificado", "contestado")
ATRIBUICOES: tuple[str, ...] = ("arquiteto", "urbanista", "engenheiro", "professor", "outro")
PAPEIS: tuple[str, ...] = ("precursor", "mestre", "discipulo")
TIPOS_FONTE: tuple[str, ...] = (
    "artigo", "livro", "capitulo", "dissertacao", "tese", "tcc", "anais",
    "entrevista", "periodico", "documento", "site", "outro",
)
TIPOS_ATUACAO: tuple[str, ...] = (
    "escola", "universidade", "orgao_publico", "escritorio", "empresa",
    "associacao", "imprensa", "laboratorio", "outro",
)

# Nós de origem para medir convergência de caminhos (GAP_BRIEF.md §1.3, §6.3).
ORIGENS_CANONICAS: tuple[str, ...] = (
    "luiz-nunes", "mario-russo", "acacio-gil-borsoi", "delfim-amorim",
)

# --------------------------------------------------------------------------- #
# Rótulos e cores (GAP_BRIEF.md §7.4) — compartilhados com o site
# --------------------------------------------------------------------------- #

ROTULOS_TIPO: dict[str, str] = {
    "heranca": "Hereditariedade",
    "mestre-aprendiz": "Mestre-aprendiz",
    "estudo": "Estudo",
    "trabalho": "Trabalho",
    "societario": "Societário",
    "dissidencia": "Dissidência",
    "coautoria-pontual": "Coautoria pontual",
}

CORES_TIPO: dict[str, str] = {
    "heranca": "#6B2D5C",
    "mestre-aprendiz": "#22527A",
    "estudo": "#4A6B4F",
    "trabalho": "#7A6420",
    "societario": "#9C3B1B",
    "dissidencia": "#B02020",
    "coautoria-pontual": "#2F6D6A",
}

ROTULOS_PAPEL: dict[str, str] = {
    "precursor": "Precursor reconhecido",
    "mestre": "Mestre / professor",
    "discipulo": "Discípulo",
    "outro": "Vínculo periférico",
}

CORES_PAPEL: dict[str, str] = {
    "precursor": "#6B2D5C",
    "mestre": "#22527A",
    "discipulo": "#9C3B1B",
    "outro": "#8A8578",
}

ROTULOS_CONFIANCA: dict[str, str] = {
    "documentado": "documentado",
    "tradicao_oral": "tradição oral",
    "hipotese": "hipótese",
}

# --------------------------------------------------------------------------- #
# Extração (GAP_BRIEF.md §4.1): Haiku por padrão, Sonnet para escalonamento.
# --------------------------------------------------------------------------- #

MODELO_EXTRACAO: str = os.environ.get("GAP_MODELO_EXTRACAO", "claude-haiku-4-5")
MODELO_ESCALONAMENTO: str = os.environ.get("GAP_MODELO_ESCALONAMENTO", "claude-sonnet-5")

AUTOR_PADRAO: str = os.environ.get("GAP_AUTOR", "paz")
