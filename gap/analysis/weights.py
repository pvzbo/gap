"""Fórmula de peso das arestas (GAP_BRIEF.md §6.2).

O peso NUNCA é armazenado nos dados: é recomputado a cada build a partir de
``confianca`` e do número de fontes independentes. Uma única função, documentada
e versionada, para que qualquer pessoa reproduza o cálculo.

    peso(aresta) = Σ_relações  w(confianca) × (1 + 0,5 × (n_fontes_independentes − 1))
    w = {documentado: 1,0; tradicao_oral: 0,6; hipotese: 0,3}

Caso-limite: relação sem nenhuma fonte (só permitida como hipótese com pendência)
tem n = 0, logo multiplicador 0,5 — ainda mais fraca do que uma hipótese com fonte.
"""
from __future__ import annotations

from typing import Any, Iterable

VERSAO_FORMULA = "1.0"

W_CONFIANCA: dict[str, float] = {
    "documentado": 1.0,
    "tradicao_oral": 0.6,
    "hipotese": 0.3,
}

BONUS_FONTE_ADICIONAL = 0.5


def n_fontes_independentes(rel: dict[str, Any]) -> int:
    """Número de fontes distintas (por id) que fundamentam a relação."""
    ids = {
        f.get("fonte")
        for f in (rel.get("fontes") or [])
        if isinstance(f, dict) and f.get("fonte")
    }
    return len(ids)


def peso_relacao(rel: dict[str, Any]) -> float:
    w = W_CONFIANCA.get(rel.get("confianca", ""), W_CONFIANCA["hipotese"])
    n = n_fontes_independentes(rel)
    return round(w * (1 + BONUS_FONTE_ADICIONAL * (n - 1)), 6)


def peso_aresta(relacoes: Iterable[dict[str, Any]]) -> float:
    return round(sum(peso_relacao(r) for r in relacoes), 6)


def descricao_formula() -> str:
    w = ", ".join(f"{k}={v}" for k, v in W_CONFIANCA.items())
    return (
        f"peso(aresta) = Σ w(confianca) × (1 + {BONUS_FONTE_ADICIONAL} × (n_fontes_independentes − 1)); "
        f"w: {w}; versão {VERSAO_FORMULA}"
    )
