"""Estágio 3 — resolução de entidades (GAP_BRIEF.md §5, estágio 3).

"Maurício do Passo Castro", "Maurício Castro", "Castro" e "o arquiteto Castro"
são um só nó. Três desfechos:

- ``auto``   — casamento inequívoco (≥ 2 tokens, score alto, sem concorrente próximo);
- ``humano`` — ambíguo, ou nome de um só token (nunca decide sozinho);
- ``novo``   — nada parecido na base; id provisório sugerido.

Quando a triagem confirma uma variante, ela entra em ``aliases.yaml``: o sistema aprende.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from rapidfuzz import fuzz, process

from ..store import Dataset, slugify
from .lexicon import normalizar

LIMIAR_AUTO = 92.0
LIMIAR_HUMANO = 72.0
MARGEM_AMBIGUIDADE = 6.0

_PREFIXOS = re.compile(
    r"^(?:o|a|os|as|do|da|de|dos|das)?\s*(?:arquiteto|arquiteta|engenheiro|engenheira|professor|professora|"
    r"prof\.?|dr\.?|dra\.?|urbanista|projetista|mestre|desenhista|jovem|então|colega|amigo|amiga|sócio|sócia|"
    r"italiano|carioca|português|portuguesa|paulista|pernambucano|pernambucana)\s+",
    re.IGNORECASE,
)
_SUFIXOS_RUIDO = re.compile(r"\s*[\(\[].*?[\)\]]\s*$")


def limpar_nome(nome: str) -> str:
    n = (nome or "").strip().strip(",.;:")
    n = _SUFIXOS_RUIDO.sub("", n)
    anterior = None
    while anterior != n:
        anterior = n
        n = _PREFIXOS.sub("", n).strip()
    return re.sub(r"\s+", " ", n)


@dataclass
class Resolucao:
    nome: str
    nome_limpo: str
    id: str | None
    score: float
    metodo: str  # exato | fuzzy | nenhum
    decisao: str  # auto | humano | novo
    motivo: str
    candidatos: list[dict[str, Any]] = field(default_factory=list)
    id_provisorio: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class Resolvedor:
    def __init__(self, ds: Dataset):
        self.ds = ds
        self.variantes: dict[str, set[str]] = {}
        for p in ds.pessoas:
            for texto in (p.get("nome"), p.get("nome_completo")):
                if texto:
                    self.variantes.setdefault(normalizar(texto), set()).add(p["id"])
        for pid, vs in ds.aliases.items():
            for v in vs:
                self.variantes.setdefault(normalizar(str(v)), set()).add(pid)
        self._choices = list(self.variantes.keys())
        self._ids_existentes = {p["id"] for p in ds.pessoas}

    def _melhores_por_id(self, norm: str) -> list[tuple[str, float, str]]:
        """[(pessoa_id, melhor_score, variante_casada)] ordenado por score desc."""
        if not self._choices:
            return []
        res = process.extract(norm, self._choices, scorer=fuzz.token_set_ratio, limit=25)
        melhor: dict[str, tuple[float, str]] = {}
        for variante, score, _ in res:
            # penaliza casar um nome longo contra uma variante de um só token ("castro")
            if len(variante.split()) == 1 and len(norm.split()) >= 2:
                score = min(score, 70.0)
            for pid in self.variantes[variante]:
                if pid not in melhor or score > melhor[pid][0]:
                    melhor[pid] = (float(score), variante)
        return sorted(((pid, s, v) for pid, (s, v) in melhor.items()), key=lambda t: (-t[1], t[0]))

    def id_provisorio(self, nome_limpo: str) -> str:
        base = slugify(nome_limpo) or "pessoa-sem-nome"
        cand = base
        n = 2
        while cand in self._ids_existentes:
            cand = f"{base}-{n}"
            n += 1
        return cand

    def resolver(self, nome: str) -> Resolucao:
        limpo = limpar_nome(nome)
        norm = normalizar(limpo)
        tokens = len([t for t in norm.split() if t not in {"de", "da", "do", "das", "dos", "e"}])
        if not norm:
            return Resolucao(nome, limpo, None, 0.0, "nenhum", "humano", "nome vazio")

        exatos = sorted(self.variantes.get(norm, set()))
        ranking = self._melhores_por_id(norm)
        candidatos = [{"id": pid, "nome": self.ds.nome(pid), "score": round(s, 1), "variante": v} for pid, s, v in ranking[:5]]

        if exatos:
            if len(exatos) == 1 and tokens >= 2:
                return Resolucao(nome, limpo, exatos[0], 100.0, "exato", "auto", "variante conhecida", candidatos)
            if len(exatos) == 1:
                return Resolucao(nome, limpo, exatos[0], 100.0, "exato", "humano", "nome de um só token — confirmar", candidatos)
            return Resolucao(nome, limpo, None, 100.0, "exato", "humano", f"variante ambígua entre {exatos}", candidatos)

        if not ranking:
            return Resolucao(nome, limpo, None, 0.0, "nenhum", "novo", "base vazia", candidatos, self.id_provisorio(limpo))

        pid, score, _var = ranking[0]
        segundo = ranking[1][1] if len(ranking) > 1 else 0.0
        if tokens < 2:
            if score >= LIMIAR_HUMANO:
                return Resolucao(nome, limpo, pid, score, "fuzzy", "humano", "nome de um só token — nunca resolve sozinho", candidatos, self.id_provisorio(limpo))
            return Resolucao(nome, limpo, None, score, "fuzzy", "humano", "nome de um só token sem correspondente claro", candidatos, self.id_provisorio(limpo))
        if score >= LIMIAR_AUTO and (score - segundo) >= MARGEM_AMBIGUIDADE:
            return Resolucao(nome, limpo, pid, score, "fuzzy", "auto", f"similaridade {score:.0f} sem concorrente próximo", candidatos)
        if score >= LIMIAR_HUMANO:
            motivo = "concorrentes próximos" if (score - segundo) < MARGEM_AMBIGUIDADE else f"similaridade {score:.0f} abaixo do limiar automático"
            return Resolucao(nome, limpo, pid, score, "fuzzy", "humano", motivo, candidatos, self.id_provisorio(limpo))
        return Resolucao(nome, limpo, None, score, "fuzzy", "novo", "sem correspondente na base", candidatos, self.id_provisorio(limpo))
