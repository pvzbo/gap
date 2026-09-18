"""Normalização de texto, léxico de gatilhos relacionais e gazetteer de nomes.

- ``normalizar``: minúsculas, sem acentos, espaços colapsados — o texto sobre o
  qual os padrões do léxico (``lexico_relacional.yaml``) são aplicados.
- ``Lexico``: carrega os padrões (regex) agrupados por tipo sugerido.
- ``Gazetteer``: nomes canônicos + ``nome_completo`` + ``aliases.yaml``; cresce
  a cada triagem confirmada.
- ``nomes_desconhecidos``: detecção de bigramas capitalizados para nomes que
  ainda não estão na base (recall primeiro; a triagem descarta o ruído).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

from ..store import Dataset


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = t.lower().replace("’", "'").replace("`", "'")
    return re.sub(r"\s+", " ", t).strip()


# --------------------------------------------------------------------------- #
# Léxico
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Gatilho:
    grupo: str
    tipo_sugerido: str | None
    termo: str


class Lexico:
    def __init__(self, grupos: dict[str, dict[str, Any]]):
        self.grupos: dict[str, dict[str, Any]] = {}
        for nome, spec in grupos.items():
            padroes = [re.compile(p, re.IGNORECASE) for p in (spec.get("padroes") or [])]
            self.grupos[nome] = {"tipo_sugerido": spec.get("tipo_sugerido"), "padroes": padroes}

    @classmethod
    def carregar(cls, path: Path) -> "Lexico":
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return cls(data)

    def gatilhos(self, texto_norm: str) -> list[Gatilho]:
        vistos: set[tuple[str, str]] = set()
        out: list[Gatilho] = []
        for grupo, spec in self.grupos.items():
            for pat in spec["padroes"]:
                for m in pat.finditer(texto_norm):
                    termo = m.group(0).strip()
                    chave = (grupo, termo)
                    if chave in vistos:
                        continue
                    vistos.add(chave)
                    out.append(Gatilho(grupo, spec["tipo_sugerido"], termo))
        return out


# --------------------------------------------------------------------------- #
# Gazetteer
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class NomeEncontrado:
    variante: str
    pessoa_id: str
    tokens: int


class Gazetteer:
    """Índice de variantes de nome → pessoa. Casamento por regex com bordas de palavra,
    do mais longo para o mais curto, para que "Mauricio do Passo Castro" não seja
    contado também como "Castro"."""

    def __init__(self, variantes: Iterable[tuple[str, str]]):
        self.variantes: dict[str, set[str]] = {}
        for texto, pid in variantes:
            v = normalizar(texto)
            if not v:
                continue
            self.variantes.setdefault(v, set()).add(pid)
        ordenadas = sorted(self.variantes, key=lambda s: (-len(s), s))
        if ordenadas:
            alt = "|".join(re.escape(v) for v in ordenadas)
            self._re = re.compile(rf"(?<![\w]){alt}(?![\w])")
        else:
            self._re = None

    @classmethod
    def do_dataset(cls, ds: Dataset) -> "Gazetteer":
        pares: list[tuple[str, str]] = []
        for p in ds.pessoas:
            pares.append((p.get("nome", ""), p["id"]))
            if p.get("nome_completo"):
                pares.append((p["nome_completo"], p["id"]))
        for pid, vs in ds.aliases.items():
            for v in vs:
                pares.append((str(v), pid))
        return cls(pares)

    def nomes(self, texto_norm: str) -> list[NomeEncontrado]:
        if self._re is None:
            return []
        out: list[NomeEncontrado] = []
        vistos: set[tuple[str, str]] = set()
        for m in self._re.finditer(texto_norm):
            v = m.group(0)
            for pid in sorted(self.variantes.get(v, ())):
                if (v, pid) in vistos:
                    continue
                vistos.add((v, pid))
                out.append(NomeEncontrado(v, pid, len(v.split())))
        return out

    def ids(self, texto_norm: str) -> set[str]:
        return {n.pessoa_id for n in self.nomes(texto_norm)}


# --------------------------------------------------------------------------- #
# Nomes desconhecidos (bigramas capitalizados)
# --------------------------------------------------------------------------- #

_MAIUSC = "A-ZÁÉÍÓÚÂÊÔÃÕÀÇÜ"
_MINUSC = "a-záéíóúâêôãõàçü"
_PALAVRA_CAP = rf"[{_MAIUSC}][{_MINUSC}]+(?:-[{_MAIUSC}]?[{_MINUSC}]+)?"
_CONECTOR = r"(?:d[aoe]s?|e|y|von|van|de la|della|di)"
_RE_NOME = re.compile(
    rf"\b({_PALAVRA_CAP}(?:\s+(?:{_CONECTOR}\s+)?{_PALAVRA_CAP}){{1,4}})"
    rf"(?:\s+(?:Neto|Filho|Júnior|Junior|Sobrinho))?\b"
)

# Palavras capitalizadas comuns em textos de arquitetura que não são nomes de pessoa.
_BLOQUEIO = {
    "escola", "belas", "artes", "universidade", "federal", "faculdade", "instituto", "departamento",
    "diretoria", "secretaria", "prefeitura", "governo", "estado", "cidade", "universitaria", "universitario",
    "recife", "pernambuco", "sao", "paulo", "rio", "janeiro", "brasil", "nordeste", "norte", "sul", "olinda",
    "joao", "pessoa", "paraiba", "bahia", "salvador", "fortaleza", "natal", "maceio", "aracaju", "lisboa", "porto",
    "arquitetura", "urbanismo", "engenharia", "moderna", "moderno", "modernismo", "brutalista", "brasileira",
    "museu", "igreja", "rua", "avenida", "praca", "edificio", "fabrica", "casa", "conjunto", "residencia",
    "hospital", "banco", "companhia", "revista", "jornal", "folha", "manha", "diario", "anais", "seminario",
    "congresso", "docomomo", "capitulo", "figura", "fonte", "tabela", "imagem", "foto", "quadro", "ver",
    "movimento", "arquitetos", "arquiteto", "arquiteta", "engenheiro", "professor", "doutor", "mestre",
    "janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
    "novembro", "dezembro", "segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo",
    "centro", "bairro", "zona", "boa", "vista", "viagem", "derby", "graças", "gracas", "espinheiro",
    "casa", "forte", "madalena", "torre", "apipucos", "varzea", "cordeiro", "pina", "encruzilhada",
    "escritorio", "tecnico", "nacional", "regional", "municipal", "publico", "obras", "contra", "secas",
    "programa", "pos-graduacao", "graduacao", "dissertacao", "tese", "mestrado", "doutorado", "orientador",
    "orientadora", "banca", "resumo", "abstract", "introducao", "conclusao", "consideracoes", "finais",
    "referencias", "bibliografia", "sumario", "agradecimentos", "lista", "figuras", "tabelas", "siglas",
    "capital", "interior", "brasileiro", "brasileiros", "portugues", "italiano", "frances", "alemao",
    "alemanha", "franca", "italia", "portugal", "estados", "unidos", "europa", "america", "latina",
    "segunda", "guerra", "mundial", "republica", "imperio", "colonia", "colonial", "sec", "seculo",
    "assim", "porem", "contudo", "entretanto", "segundo", "conforme", "ainda", "embora", "quando",
    "durante", "depois", "antes", "apos", "entre", "sobre", "para", "pela", "pelo", "nesse", "nessa",
    "neste", "nesta", "esse", "essa", "este", "esta", "outro", "outra", "todos", "todas", "cada",
    "grande", "pequeno", "novo", "nova", "velho", "antigo", "primeiro", "primeira", "ultimo", "ultima",
    "santo", "santa", "senhor", "senhora", "nossa", "nosso", "bom", "jesus", "cristo", "deus",
    "premio", "concurso", "projeto", "plano", "diretor", "obra", "construcao", "construtora", "empresa",
    "avant", "bresil", "vitruvius", "arquitextos", "projeto", "au", "cau", "iab", "crea",
}


def nomes_desconhecidos(texto: str, gazetteer: Gazetteer | None = None) -> list[str]:
    out: list[str] = []
    vistos: set[str] = set()
    for m in _RE_NOME.finditer(texto or ""):
        cand = m.group(0).strip()
        tokens = [t for t in re.split(r"\s+", cand)]
        principais = [t for t in tokens if t.lower() not in {"de", "da", "do", "das", "dos", "e", "y", "von", "van", "di", "della", "la"}]
        if len(principais) < 2:
            continue
        norm_tokens = [normalizar(t) for t in principais]
        if any(t in _BLOQUEIO for t in norm_tokens):
            continue
        n = normalizar(cand)
        if gazetteer is not None and gazetteer.nomes(n):
            continue
        if n in vistos:
            continue
        vistos.add(n)
        out.append(cand)
    return out
