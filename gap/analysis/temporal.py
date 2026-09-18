"""Camada temporal (GAP_BRIEF.md §2 "Temporal layer", §6.3 "Temporal").

O tempo é métrica sempre que existe. Nesta versão:
- ``parse_periodo`` interpreta os formatos aceitos em ``periodo``;
- fatias por década (relações ativas na década) e acumulado (rede "nascendo");
- linha do tempo por pessoa, usada na página de pessoa do site.

Regra conservadora: um período aberto ("1954-") vale, para fatiamento, apenas
pelo ano documentado de início. Não se prolonga o que a fonte não afirma.
"""
from __future__ import annotations

import re
from typing import Any

import networkx as nx

from ..store import Dataset
from .graph import construir_grafo, componentes, sem_isolados

_RE_INTERVALO = re.compile(r"^(?:c\.|ca\.)?\s*(\d{4})\s*-\s*(\d{4})?$")
_RE_ANO = re.compile(r"^(?:c\.|ca\.)?\s*(\d{4})$")
_RE_ATE = re.compile(r"^-\s*(\d{4})$")
_RE_DECADA = re.compile(r"^(?:anos|d[ée]cada de)\s+(\d{4})$", re.IGNORECASE)


def parse_periodo(valor: Any) -> tuple[int | None, int | None] | None:
    """"1950-1954" → (1950, 1954); "1954-" → (1954, None); "1958" → (1958, 1958);
    "-1937" → (None, 1937); "anos 1950" → (1950, 1959). Inválido → None."""
    if valor is None:
        return None
    s = str(valor).strip()
    if not s:
        return None
    m = _RE_INTERVALO.match(s)
    if m:
        ini = int(m.group(1))
        fim = int(m.group(2)) if m.group(2) else None
        return (ini, fim)
    m = _RE_ANO.match(s)
    if m:
        a = int(m.group(1))
        return (a, a)
    m = _RE_ATE.match(s)
    if m:
        return (None, int(m.group(1)))
    m = _RE_DECADA.match(s)
    if m:
        d = int(m.group(1)) // 10 * 10
        return (d, d + 9)
    return None


def decada(ano: int) -> int:
    return ano // 10 * 10


def intervalo_efetivo(rel: dict[str, Any]) -> tuple[int, int] | None:
    """Intervalo fechado usado para fatiar. Aberto → colapsa no ano conhecido."""
    p = parse_periodo(rel.get("periodo"))
    if p is None:
        return None
    ini, fim = p
    if ini is None and fim is None:
        return None
    if ini is None:
        ini = fim
    if fim is None:
        fim = ini
    return (int(ini), int(fim))


def _resumo_grafo(G: nx.Graph) -> dict[str, Any]:
    H = sem_isolados(G)
    comps = componentes(H)
    maior = len(comps[0]) if comps else 0
    return {
        "n_nos": H.number_of_nodes(),
        "n_arestas": H.number_of_edges(),
        "n_componentes": len(comps),
        "maior_componente": maior,
        "densidade": round(nx.density(H), 4) if H.number_of_nodes() > 1 else 0.0,
        "agrupamento_medio": round(nx.average_clustering(H), 4) if H.number_of_nodes() > 0 else 0.0,
    }


def fatias_por_decada(ds: Dataset, relacoes: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    rels = relacoes if relacoes is not None else ds.relacoes
    datadas = [(r, intervalo_efetivo(r)) for r in rels]
    datadas = [(r, iv) for r, iv in datadas if iv is not None]
    if not datadas:
        return []
    anos_ini = [iv[0] for _, iv in datadas]
    anos_fim = [iv[1] for _, iv in datadas]
    d0, d1 = decada(min(anos_ini)), decada(max(anos_fim))
    saida = []
    for d in range(d0, d1 + 1, 10):
        a, b = d, d + 9
        ativas = [r for r, (i, f) in datadas if i <= b and f >= a]
        acumuladas = [r for r, (i, _f) in datadas if i <= b]
        saida.append(
            {
                "decada": d,
                "rotulo": f"anos {d}",
                "fatia": {"n_relacoes": len(ativas), **_resumo_grafo(construir_grafo(ds, ativas))},
                "acumulado": {"n_relacoes": len(acumuladas), **_resumo_grafo(construir_grafo(ds, acumuladas))},
            }
        )
    return saida


def cobertura_temporal(ds: Dataset, relacoes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rels = relacoes if relacoes is not None else ds.relacoes
    com = sum(1 for r in rels if intervalo_efetivo(r) is not None)
    invalidos = [r["id"] for r in rels if r.get("periodo") and parse_periodo(r.get("periodo")) is None]
    pessoas_datadas = sum(
        1
        for p in ds.pessoas
        if p.get("nascimento")
        or any((f.get("ano_inicio") or f.get("ano_conclusao")) for f in (p.get("formacao") or []))
    )
    return {
        "n_relacoes": len(rels),
        "n_com_periodo": com,
        "proporcao_com_periodo": round(com / len(rels), 4) if rels else 0.0,
        "periodos_invalidos": invalidos,
        "n_pessoas_com_datas": pessoas_datadas,
        "n_pessoas": len(ds.pessoas),
    }


def eventos_pessoa(p: dict[str, Any], relacoes: list[dict[str, Any]], ds: Dataset) -> list[dict[str, Any]]:
    """Linha do tempo de uma pessoa: datas biográficas, formação, atuação e relações datadas."""
    ev: list[dict[str, Any]] = []
    if p.get("nascimento"):
        ev.append({"ano": p["nascimento"], "fim": None, "tipo": "nascimento", "rotulo": "Nascimento"})
    for f in p.get("formacao") or []:
        ini, fim = f.get("ano_inicio"), f.get("ano_conclusao")
        if ini or fim:
            inst = ds.instituicoes_por_id.get(f.get("instituicao"), {}).get("nome") or f.get("instituicao")
            ev.append({"ano": ini or fim, "fim": fim, "tipo": "formacao", "rotulo": f"{f.get('curso') or 'Formação'} — {inst}"})
    for a in p.get("atuacao") or []:
        iv = parse_periodo(a.get("periodo"))
        if iv and (iv[0] or iv[1]):
            inst = ds.instituicoes_por_id.get(a.get("nome"), {}).get("nome") or a.get("nome")
            ev.append({"ano": iv[0] or iv[1], "fim": iv[1], "tipo": "atuacao", "rotulo": f"{a.get('papel') or 'Atuação'} — {inst}"})
    for r in relacoes:
        iv = parse_periodo(r.get("periodo"))
        if iv and (iv[0] or iv[1]):
            outro = r["destino"] if r["origem"] == p["id"] else r["origem"]
            ev.append(
                {
                    "ano": iv[0] or iv[1],
                    "fim": iv[1],
                    "tipo": "relacao",
                    "subtipo": r["tipo"],
                    "rotulo": f"{r['tipo']} — {ds.nome(outro)}",
                    "relacao": r["id"],
                    "outro": outro,
                }
            )
    if p.get("morte"):
        ev.append({"ano": p["morte"], "fim": None, "tipo": "morte", "rotulo": "Morte"})
    ev.sort(key=lambda e: (e["ano"] or 0, e["tipo"]))
    return ev
