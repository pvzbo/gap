"""Construção do grafo a partir do conjunto de dados (GAP_BRIEF.md §6.1).

Dois níveis que nunca se confundem:

- **relações**: linhas de ``relacoes.jsonl``. Conte-as quando a pergunta for
  "quantas relações societárias existem".
- **arestas**: pares únicos de pessoas. O grafo colapsa as relações de um par
  em uma aresta com ``tipos=[...]`` e ``peso`` somado. Métricas rodam em arestas.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

import networkx as nx

from ..config import TIPOS_DIRECIONAIS, TIPOS_RELACAO
from ..store import Dataset
from .weights import peso_aresta


def par_nao_ordenado(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def filtrar_relacoes(
    relacoes: Iterable[dict[str, Any]],
    *,
    tipos: Iterable[str] | None = None,
    incluir_hipoteses: bool = True,
    confiancas: Iterable[str] | None = None,
    status: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    tipos_set = set(tipos) if tipos is not None else None
    conf_set = set(confiancas) if confiancas is not None else None
    status_set = set(status) if status is not None else None
    out = []
    for r in relacoes:
        if tipos_set is not None and r.get("tipo") not in tipos_set:
            continue
        if not incluir_hipoteses and r.get("confianca") == "hipotese":
            continue
        if conf_set is not None and r.get("confianca") not in conf_set:
            continue
        if status_set is not None and r.get("status") not in status_set:
            continue
        out.append(r)
    return out


def _atributos_no(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "nome": p.get("nome") or p["id"],
        "atribuicao": p.get("atribuicao") or "",
        "papel": p.get("papel_historiografico") or "outro",
        "status": p.get("status") or "rascunho",
        "nascimento": p.get("nascimento"),
        "morte": p.get("morte"),
    }


def construir_grafo(
    ds: Dataset,
    relacoes: list[dict[str, Any]] | None = None,
    *,
    tipos: Iterable[str] | None = None,
    incluir_hipoteses: bool = True,
    incluir_isolados: bool = True,
) -> nx.Graph:
    """Grafo não dirigido de pessoas; uma aresta por par, com relações agregadas."""
    rels = filtrar_relacoes(
        relacoes if relacoes is not None else ds.relacoes,
        tipos=tipos,
        incluir_hipoteses=incluir_hipoteses,
    )
    G = nx.Graph()
    if incluir_isolados:
        for p in ds.pessoas:
            G.add_node(p["id"], **_atributos_no(p))

    pessoas = ds.pessoas_por_id
    grupos: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rels:
        grupos[par_nao_ordenado(r["origem"], r["destino"])].append(r)

    for (a, b), grupo in grupos.items():
        for n in (a, b):
            if n not in G:
                G.add_node(n, **_atributos_no(pessoas.get(n, {"id": n})))
        contagem = Counter(r["tipo"] for r in grupo)
        tipos_par = sorted(contagem, key=TIPOS_RELACAO.index)
        dominante = max(tipos_par, key=lambda t: (contagem[t], -TIPOS_RELACAO.index(t)))
        peso = peso_aresta(grupo)
        confs = sorted({r.get("confianca", "hipotese") for r in grupo})
        fontes = {
            f.get("fonte")
            for r in grupo
            for f in (r.get("fontes") or [])
            if isinstance(f, dict) and f.get("fonte")
        }
        G.add_edge(
            a,
            b,
            peso=peso,
            distancia=(1.0 / peso) if peso > 0 else 10.0,
            tipos=tipos_par,
            tipo_dominante=dominante,
            n_relacoes=len(grupo),
            relacoes=[r["id"] for r in grupo],
            confiancas=confs,
            apenas_hipotese=all(r.get("confianca") == "hipotese" for r in grupo),
            n_fontes=len(fontes),
        )
    return G


def construir_digrafo(
    ds: Dataset,
    relacoes: list[dict[str, Any]] | None = None,
    *,
    tipos: Iterable[str] | None = None,
    incluir_hipoteses: bool = True,
) -> nx.DiGraph:
    """Grafo dirigido origem → destino apenas para relações direcionais (não simétricas)."""
    tipos_set = set(tipos) if tipos is not None else TIPOS_DIRECIONAIS
    rels = filtrar_relacoes(
        relacoes if relacoes is not None else ds.relacoes,
        tipos=tipos_set,
        incluir_hipoteses=incluir_hipoteses,
    )
    D = nx.DiGraph()
    pessoas = ds.pessoas_por_id
    for r in rels:
        if r.get("simetrico"):
            continue
        for n in (r["origem"], r["destino"]):
            if n not in D:
                D.add_node(n, **_atributos_no(pessoas.get(n, {"id": n})))
        if D.has_edge(r["origem"], r["destino"]):
            D[r["origem"]][r["destino"]]["relacoes"].append(r["id"])
            D[r["origem"]][r["destino"]]["tipos"] = sorted(
                set(D[r["origem"]][r["destino"]]["tipos"]) | {r["tipo"]}, key=TIPOS_RELACAO.index
            )
        else:
            D.add_edge(r["origem"], r["destino"], relacoes=[r["id"]], tipos=[r["tipo"]])
    return D


def subgrafo_tipo(ds: Dataset, tipo: str, *, incluir_hipoteses: bool = True) -> nx.Graph:
    """Subgrafo com apenas um tipo de relação, sem nós isolados."""
    return construir_grafo(ds, tipos=[tipo], incluir_hipoteses=incluir_hipoteses, incluir_isolados=False)


def sem_isolados(G: nx.Graph) -> nx.Graph:
    return G.subgraph([n for n, d in G.degree() if d > 0]).copy()


def componentes(G: nx.Graph) -> list[set[str]]:
    return sorted(nx.connected_components(G), key=lambda c: (-len(c), sorted(c)[0]))


def maior_componente(G: nx.Graph) -> nx.Graph:
    comps = componentes(G)
    if not comps:
        return nx.Graph()
    return G.subgraph(comps[0]).copy()


def ego(G: nx.Graph, no: str, raio: int = 2) -> nx.Graph:
    """Ego-rede (GAP_BRIEF.md §6.4) com vizinhos anotados por salto."""
    if no not in G:
        return nx.Graph()
    E = nx.ego_graph(G, no, radius=raio)
    dist = nx.single_source_shortest_path_length(E, no)
    for n, d in dist.items():
        E.nodes[n]["saltos"] = d
    return E
