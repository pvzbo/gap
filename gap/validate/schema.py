"""Esquemas pydantic das quatro entidades (GAP_BRIEF.md §3.1–3.4).

``extra="forbid"`` faz um campo com nome errado falhar na validação em vez de
ser silenciosamente ignorado — a proteção mais barata contra dados sujos.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ID_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"

TipoRelacao = Literal[
    "heranca", "mestre-aprendiz", "estudo", "trabalho",
    "societario", "dissidencia", "coautoria-pontual",
]
Confianca = Literal["documentado", "tradicao_oral", "hipotese"]
Status = Literal["rascunho", "verificado", "contestado"]
Atribuicao = Literal["arquiteto", "urbanista", "engenheiro", "professor", "outro"]
Papel = Literal["precursor", "mestre", "discipulo"]
TipoFonte = Literal[
    "artigo", "livro", "capitulo", "dissertacao", "tese", "tcc", "anais",
    "entrevista", "periodico", "documento", "site", "outro",
]
TipoAtuacao = Literal[
    "escola", "universidade", "orgao_publico", "escritorio", "empresa",
    "associacao", "imprensa", "laboratorio", "outro",
]
Densidade = Literal["alta", "media", "baixa"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FormacaoItem(_Base):
    instituicao: str
    curso: str | None = None
    ano_inicio: int | None = None
    ano_conclusao: int | None = None


class AtuacaoItem(_Base):
    tipo: TipoAtuacao | None = None
    nome: str
    papel: str | None = None
    periodo: str | None = None


class Pessoa(_Base):
    id: str = Field(pattern=ID_PATTERN)
    nome: str = Field(min_length=1)
    nome_completo: str | None = None
    nascimento: int | None = None
    morte: int | None = None
    local_nascimento: str | None = None
    titulo_epoca: str | None = None
    atribuicao: Atribuicao | None = None
    papel_historiografico: Papel | None = None
    formacao: list[FormacaoItem] = Field(default_factory=list)
    atuacao: list[AtuacaoItem] = Field(default_factory=list)
    notas: str | None = None
    status: Status = "rascunho"
    fontes: list[str] = Field(default_factory=list)
    pendencia: str | None = None
    data_entrada: str | None = None
    autor_entrada: str | None = None

    @model_validator(mode="after")
    def _datas_coerentes(self) -> "Pessoa":
        if self.nascimento and self.morte and self.morte < self.nascimento:
            raise ValueError("morte anterior ao nascimento")
        return self


class FonteRef(_Base):
    fonte: str
    pagina: str | None = None
    trecho: str | None = None


class Relacao(_Base):
    id: str = Field(pattern=r"^rel-\d{4,}$")
    origem: str = Field(pattern=ID_PATTERN)
    destino: str = Field(pattern=ID_PATTERN)
    tipo: TipoRelacao
    subtipo: str | None = None
    simetrico: bool = False
    periodo: str | None = None
    descricao: str | None = None
    confianca: Confianca
    fontes: list[FonteRef] = Field(default_factory=list)
    pendencia: str | None = None
    rompe: str | None = None
    status: Status = "rascunho"
    data_entrada: str | None = None
    autor_entrada: str | None = None

    @model_validator(mode="after")
    def _regras(self) -> "Relacao":
        if self.origem == self.destino:
            raise ValueError("origem e destino são a mesma pessoa")
        return self


class Depoimento(_Base):
    id: str = Field(pattern=r"^dep-\d{4,}$")
    pessoa: str = Field(pattern=ID_PATTERN)
    existe_escola: bool | None
    argumento: str = Field(min_length=1)
    fonte: FonteRef
    data_depoimento: str | None = None
    status: Status = "rascunho"
    data_entrada: str | None = None
    autor_entrada: str | None = None


class Fonte(_Base):
    id: str = Field(pattern=ID_PATTERN)
    tipo: TipoFonte = "outro"
    autor: str | None = None
    titulo: str | None = None
    veiculo: str | None = None
    ano: int | None = None
    url: str | None = None
    arquivo_local: str | None = None
    paginas: int | None = None
    processado: bool = False
    densidade: Densidade | None = None
    prioridade: int | None = None
    notas: str | None = None
    metadados_automaticos: bool = False
