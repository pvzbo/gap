"""Métricas computadas a cada build (GAP_BRIEF.md §1.3 e §6.3).

Cada bloco corresponde a um critério teórico do contrato analítico:

- comunidades / modularidade ............ identidade de grupo restrito (Zein 3, 4)
- convergência de origens ............... origens comuns (Zein 2)
- proselitismo .......................... transmissão deliberada (Zein 5)
- agrupamento / caminho médio ........... coesão informal / colégio invisível (Crane)
- centralidades ......................... círculo esotérico vs. exotérico (Fleck)
- componentes / pontes ausentes ......... dissidência estruturante (Bourdieu)
- auditoria de confiança por tipo ....... tópos narrativo (Kris & Kurz)

Nenhuma métrica decide sozinha. O relatório diz sob quais critérios o conjunto
se qualifica como escola e sob quais não.
"""
from __future__ import annotations

import datetime as _dt
import itertools
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import networkx as nx
from networkx.algorithms.community import louvain_communities, modularity

from ..config import ORIGENS_CANONICAS, ROTULOS_TIPO, TIPOS_ENSINO, TIPOS_RELACAO, Paths
from ..store import Dataset, read_jsonl
from .graph import componentes, construir_grafo, construir_digrafo, maior_componente, sem_isolados
from .temporal import cobertura_temporal, fatias_por_decada
from .weights import VERSAO_FORMULA, descricao_formula

SEED = 42


def _r(x: float | None, nd: int = 4) -> float | None:
    return None if x is None else round(float(x), nd)


# --------------------------------------------------------------------------- #
# Comunidades
# --------------------------------------------------------------------------- #

def comunidades(G: nx.Graph, seed: int = SEED) -> tuple[dict[str, int], float | None, list[list[str]]]:
    H = sem_isolados(G)
    if H.number_of_edges() == 0:
        return {}, None, []
    comms = louvain_communities(H, weight="peso", seed=seed)
    comms = sorted((sorted(c) for c in comms), key=lambda c: (-len(c), c[0]))
    mod = modularity(H, [set(c) for c in comms], weight="peso")
    atrib = {n: i for i, c in enumerate(comms) for n in c}
    return atrib, float(mod), comms


# --------------------------------------------------------------------------- #
# Métricas por nó
# --------------------------------------------------------------------------- #

def metricas_nos(G: nx.Graph, origens: tuple[str, ...] = ORIGENS_CANONICAS) -> dict[str, dict[str, Any]]:
    grau = dict(G.degree())
    forca = dict(G.degree(weight="peso"))
    if G.number_of_edges():
        inter = nx.betweenness_centrality(G, weight="distancia", normalized=True)
        prox = nx.closeness_centrality(G, distance="distancia")
    else:
        inter = {n: 0.0 for n in G}
        prox = {n: 0.0 for n in G}

    autov: dict[str, float] = {n: 0.0 for n in G}
    C = maior_componente(sem_isolados(G))
    if C.number_of_edges():
        try:
            autov.update(nx.eigenvector_centrality(C, weight="peso", max_iter=5000, tol=1e-6))
        except nx.PowerIterationFailedConvergence:  # pragma: no cover
            autov.update(nx.eigenvector_centrality_numpy(C, weight="peso"))

    comps = componentes(G)
    comp_idx = {n: i for i, c in enumerate(comps) for n in c}
    comp_tam = {n: len(c) for c in comps for n in c}
    com_idx, _mod, _ = comunidades(G)

    saltos_por_origem: dict[str, dict[str, int]] = {}
    for o in origens:
        if o in G:
            saltos_por_origem[o] = nx.single_source_shortest_path_length(G, o)

    out: dict[str, dict[str, Any]] = {}
    for n in G.nodes:
        out[n] = {
            "grau": int(grau.get(n, 0)),
            "forca": _r(forca.get(n, 0.0), 3),
            "intermediacao": _r(inter.get(n, 0.0)),
            "proximidade": _r(prox.get(n, 0.0)),
            "autovetor": _r(autov.get(n, 0.0)),
            "componente": comp_idx.get(n),
            "tamanho_componente": comp_tam.get(n, 1),
            "comunidade": com_idx.get(n),
            "isolado": grau.get(n, 0) == 0,
            "saltos": {o: d.get(n) for o, d in saltos_por_origem.items()},
        }
    return out


def ranking(nos: dict[str, dict[str, Any]], ds: Dataset, chave: str, k: int = 10) -> list[dict[str, Any]]:
    itens = sorted(nos.items(), key=lambda kv: (-(kv[1].get(chave) or 0), kv[0]))
    return [
        {"id": n, "nome": ds.nome(n), chave: m.get(chave)}
        for n, m in itens[:k]
        if (m.get(chave) or 0) > 0
    ]


# --------------------------------------------------------------------------- #
# Métricas globais
# --------------------------------------------------------------------------- #

def _papeis(ds: Dataset, ids: list[str]) -> dict[str, int]:
    c = Counter((ds.pessoas_por_id.get(i, {}).get("papel_historiografico") or "outro") for i in ids)
    return dict(sorted(c.items()))


def _atribuicoes(ds: Dataset, ids: list[str]) -> dict[str, int]:
    c = Counter((ds.pessoas_por_id.get(i, {}).get("atribuicao") or "indefinida") for i in ids)
    return dict(sorted(c.items()))


def metricas_grafo(G: nx.Graph, ds: Dataset, relacoes: list[dict[str, Any]]) -> dict[str, Any]:
    H = sem_isolados(G)
    comps = componentes(H)
    C = maior_componente(H)
    com_idx, mod, comms = comunidades(G)

    caminho_medio = diametro = None
    if C.number_of_nodes() > 1:
        caminho_medio = nx.average_shortest_path_length(C)
        diametro = nx.diameter(C)

    dist_grau = Counter(d for _, d in G.degree())
    return {
        "n_pessoas": G.number_of_nodes(),
        "n_relacoes": len(relacoes),
        "n_arestas": G.number_of_edges(),
        "n_conectados": H.number_of_nodes(),
        "n_isolados": G.number_of_nodes() - H.number_of_nodes(),
        "n_componentes": len(comps),
        "componentes": [
            {"id": i, "tamanho": len(c), "membros": sorted(c), "papeis": _papeis(ds, sorted(c))}
            for i, c in enumerate(comps)
        ],
        "maior_componente": C.number_of_nodes(),
        "proporcao_no_maior_componente": _r(C.number_of_nodes() / G.number_of_nodes()) if G.number_of_nodes() else 0.0,
        "densidade_global": _r(nx.density(G)) if G.number_of_nodes() > 1 else 0.0,
        "densidade_conectados": _r(nx.density(H)) if H.number_of_nodes() > 1 else 0.0,
        "agrupamento_medio": _r(nx.average_clustering(H)) if H.number_of_nodes() else 0.0,
        "transitividade": _r(nx.transitivity(H)) if H.number_of_nodes() else 0.0,
        "caminho_medio_maior_componente": _r(caminho_medio),
        "diametro_maior_componente": diametro,
        "modularidade": _r(mod),
        "n_comunidades": len(comms),
        "comunidades": [
            {
                "id": i,
                "tamanho": len(c),
                "membros": c,
                "papeis": _papeis(ds, c),
                "atribuicoes": _atribuicoes(ds, c),
            }
            for i, c in enumerate(comms)
        ],
        "distribuicao_grau": {str(k): v for k, v in sorted(dist_grau.items())},
        "grau_medio": _r(sum(d for _, d in G.degree()) / G.number_of_nodes()) if G.number_of_nodes() else 0.0,
        "peso_total": _r(sum(d["peso"] for _, _, d in G.edges(data=True)), 3),
    }


# --------------------------------------------------------------------------- #
# Por tipo de relação
# --------------------------------------------------------------------------- #

def metricas_por_tipo(ds: Dataset, relacoes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for tipo in TIPOS_RELACAO:
        rels = [r for r in relacoes if r.get("tipo") == tipo]
        G = construir_grafo(ds, rels, incluir_isolados=False)
        comps = componentes(G)
        C = maior_componente(G)
        grau = sorted(G.degree(), key=lambda kv: (-kv[1], kv[0]))
        out[tipo] = {
            "rotulo": ROTULOS_TIPO[tipo],
            "n_relacoes": len(rels),
            "n_nos": G.number_of_nodes(),
            "n_arestas": G.number_of_edges(),
            "n_componentes": len(comps),
            "maior_componente": C.number_of_nodes(),
            "densidade": _r(nx.density(G)) if G.number_of_nodes() > 1 else 0.0,
            "agrupamento_medio": _r(nx.average_clustering(G)) if G.number_of_nodes() else 0.0,
            "caminho_medio_maior_componente": _r(nx.average_shortest_path_length(C)) if C.number_of_nodes() > 1 else None,
            "confiancas": dict(Counter(r.get("confianca") for r in rels)),
            "top_grau": [{"id": n, "nome": ds.nome(n), "grau": d} for n, d in grau[:5]],
            "proporcao_com_periodo": _r(sum(1 for r in rels if r.get("periodo")) / len(rels)) if rels else None,
        }
    return out


# --------------------------------------------------------------------------- #
# Auditoria de confiança (Kris & Kurz)
# --------------------------------------------------------------------------- #

def auditoria_confianca(relacoes: list[dict[str, Any]]) -> dict[str, Any]:
    por_tipo: dict[str, dict[str, Any]] = {}
    for tipo in TIPOS_RELACAO:
        rels = [r for r in relacoes if r.get("tipo") == tipo]
        c = Counter(r.get("confianca") for r in rels)
        total = len(rels)
        por_tipo[tipo] = {
            "documentado": c.get("documentado", 0),
            "tradicao_oral": c.get("tradicao_oral", 0),
            "hipotese": c.get("hipotese", 0),
            "total": total,
            "proporcao_documentado": _r(c.get("documentado", 0) / total) if total else None,
        }
    ctot = Counter(r.get("confianca") for r in relacoes)
    total = len(relacoes)

    def prop(tipos: set[str]) -> float | None:
        rels = [r for r in relacoes if r.get("tipo") in tipos]
        if not rels:
            return None
        return sum(1 for r in rels if r.get("confianca") == "documentado") / len(rels)

    p_ensino = prop(set(TIPOS_ENSINO))
    p_pratica = prop({"societario", "trabalho", "coautoria-pontual"})
    if p_ensino is None or p_pratica is None:
        leitura = "Amostra insuficiente para comparar ensino e prática profissional."
    elif p_pratica - p_ensino > 0.2:
        leitura = (
            "Relações de ensino (estudo, mestre-aprendiz) são sistematicamente menos documentadas "
            "que as de prática (societário, trabalho, coautoria): suspeita de tópos narrativo mestre-discípulo (Kris & Kurz)."
        )
    else:
        leitura = (
            "Relações de ensino e de prática têm proporção de documentação comparável: "
            "sem sinal, nesta base, de convenção narrativa mestre-discípulo."
        )
    return {
        "por_tipo": por_tipo,
        "total": {
            "documentado": ctot.get("documentado", 0),
            "tradicao_oral": ctot.get("tradicao_oral", 0),
            "hipotese": ctot.get("hipotese", 0),
            "total": total,
            "proporcao_documentado": _r(ctot.get("documentado", 0) / total) if total else None,
        },
        "proporcao_documentado_ensino": _r(p_ensino),
        "proporcao_documentado_pratica": _r(p_pratica),
        "leitura": leitura,
    }


# --------------------------------------------------------------------------- #
# Convergência de origens (Zein 2)
# --------------------------------------------------------------------------- #

def convergencia_origens(G: nx.Graph, ds: Dataset, origens: tuple[str, ...] = ORIGENS_CANONICAS) -> dict[str, Any]:
    H = sem_isolados(G)
    presentes = [o for o in origens if o in H]
    alcance: dict[str, Any] = {}
    n_nao_origem = max(H.number_of_nodes() - len(presentes), 1)
    for o in presentes:
        dist = nx.single_source_shortest_path_length(H, o)
        por_salto = Counter(d for n, d in dist.items() if n != o)
        alcancaveis = sum(1 for n in dist if n != o)
        alcance[o] = {
            "nome": ds.nome(o),
            "grau": H.degree(o),
            "saltos_1": por_salto.get(1, 0),
            "saltos_2": por_salto.get(2, 0),
            "saltos_3": por_salto.get(3, 0),
            "alcancaveis": alcancaveis,
            "proporcao_alcancavel": _r(alcancaveis / n_nao_origem),
        }
    ausentes = [o for o in origens if o in G and o not in H]

    pares = 0
    via = 0
    por_origem: Counter[str] = Counter()
    if presentes and H.number_of_edges():
        dist_all = dict(nx.all_pairs_shortest_path_length(H))
        nos = [n for n in H if n not in presentes]
        for u, v in itertools.combinations(nos, 2):
            du = dist_all.get(u, {})
            if v not in du:
                continue
            d = du[v]
            pares += 1
            passou = False
            for o in presentes:
                if o in du and v in dist_all.get(o, {}) and du[o] + dist_all[o][v] == d:
                    por_origem[o] += 1
                    passou = True
            if passou:
                via += 1
    return {
        "origens": list(origens),
        "presentes_conectadas": presentes,
        "presentes_isoladas": ausentes,
        "alcance": alcance,
        "caminhos": {
            "pares_avaliados": pares,
            "pares_via_alguma_origem": via,
            "proporcao": _r(via / pares) if pares else None,
            "por_origem": {o: por_origem.get(o, 0) for o in presentes},
        },
        "leitura": (
            "Sem origens conectadas: não é possível medir convergência."
            if not presentes
            else (
                f"{_r(via / pares * 100, 1) if pares else 0}% dos caminhos mais curtos entre não-origens passam por "
                f"ao menos uma origem canônica ({', '.join(ds.nome(o) for o in presentes)})."
                + (f" Origens isoladas na base atual: {', '.join(ds.nome(o) for o in ausentes)}." if ausentes else "")
            )
        ),
    }


# --------------------------------------------------------------------------- #
# Proselitismo (Zein 5)
# --------------------------------------------------------------------------- #

def proselitismo(ds: Dataset, relacoes: list[dict[str, Any]]) -> dict[str, Any]:
    D = construir_digrafo(ds, relacoes, tipos=TIPOS_ENSINO)
    n_arestas = D.number_of_edges()
    saida = sorted(((n, d) for n, d in D.out_degree() if d > 0), key=lambda kv: (-kv[1], kv[0]))
    entrada = sorted(((n, d) for n, d in D.in_degree() if d > 0), key=lambda kv: (-kv[1], kv[0]))
    top3 = sum(d for _, d in saida[:3])
    n_rel_ensino = sum(1 for r in relacoes if r.get("tipo") in TIPOS_ENSINO)
    return {
        "n_relacoes_ensino": n_rel_ensino,
        "n_arestas_dirigidas": n_arestas,
        "n_emissores": len(saida),
        "n_receptores": len(entrada),
        "emissores": [{"id": n, "nome": ds.nome(n), "saida": d} for n, d in saida],
        "receptores": [{"id": n, "nome": ds.nome(n), "entrada": d} for n, d in entrada[:15]],
        "concentracao_top3": _r(top3 / n_arestas) if n_arestas else None,
        "leitura": (
            "Sem arestas de ensino na base."
            if not n_arestas
            else f"{len(saida)} emissor(es) para {len(entrada)} receptor(es); os três maiores emissores "
            f"concentram {_r(top3 / n_arestas * 100, 1)}% das arestas de ensino. "
            + ("Transmissão concentrada em poucos nós." if top3 / n_arestas >= 0.6 else "Transmissão dispersa.")
        ),
    }


# --------------------------------------------------------------------------- #
# Cobertura e pendências
# --------------------------------------------------------------------------- #

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().lower()


def mencoes_sem_relacao(ds: Dataset, paths: Paths | None) -> list[dict[str, Any]]:
    """Agrega ``mencoes_sem_relacao`` de work/<fonte>/extraidos.jsonl (pistas de pesquisa)."""
    if paths is None or not paths.work.exists():
        return []
    conhecidos: set[str] = set()
    for p in ds.pessoas:
        conhecidos.add(_norm(p.get("nome", "")))
        if p.get("nome_completo"):
            conhecidos.add(_norm(p["nome_completo"]))
    for pid, vs in ds.aliases.items():
        conhecidos.update(_norm(v) for v in vs)
    agg: dict[str, dict[str, Any]] = {}
    for pasta in sorted(paths.work.iterdir()):
        arq = pasta / "extraidos.jsonl"
        if not pasta.is_dir() or not arq.exists():
            continue
        for row in read_jsonl(arq):
            for nome in row.get("mencoes_sem_relacao") or []:
                if not isinstance(nome, str):
                    continue
                k = _norm(nome)
                if not k or k in conhecidos or len(k.split()) < 2:
                    continue
                e = agg.setdefault(k, {"nome": nome.strip(), "n": 0, "fontes": set()})
                e["n"] += 1
                e["fontes"].add(pasta.name)
    saida = [{"nome": e["nome"], "n": e["n"], "fontes": sorted(e["fontes"])} for e in agg.values()]
    saida.sort(key=lambda e: (-e["n"], e["nome"]))
    return saida[:100]


def cobertura(ds: Dataset, G: nx.Graph, paths: Paths | None = None) -> dict[str, Any]:
    isolados = [
        {"id": n, "nome": ds.nome(n), "papel": ds.pessoas_por_id.get(n, {}).get("papel_historiografico")}
        for n, d in G.degree()
        if d == 0
    ]
    pend: list[dict[str, Any]] = []
    for p in ds.pessoas:
        if (p.get("pendencia") or "").strip():
            pend.append({"entidade": "pessoa", "id": p["id"], "nome": p.get("nome"), "pendencia": p["pendencia"]})
    for r in ds.relacoes:
        if (r.get("pendencia") or "").strip():
            pend.append(
                {
                    "entidade": "relacao",
                    "id": r["id"],
                    "nome": f"{ds.nome(r['origem'])} → {ds.nome(r['destino'])} ({r['tipo']})",
                    "pendencia": r["pendencia"],
                }
            )
    fontes_proc = [f["id"] for f in ds.fontes if f.get("processado")]
    fontes_nao = [f["id"] for f in ds.fontes if not f.get("processado")]
    return {
        "isolados": sorted(isolados, key=lambda x: x["nome"]),
        "n_isolados": len(isolados),
        "pendencias": pend,
        "n_pendencias": len(pend),
        "fontes": {"total": len(ds.fontes), "processadas": fontes_proc, "nao_processadas": fontes_nao},
        "mencoes_sem_relacao": mencoes_sem_relacao(ds, paths),
        "status_relacoes": dict(Counter(r.get("status") for r in ds.relacoes)),
        "status_pessoas": dict(Counter(p.get("status") for p in ds.pessoas)),
    }


# --------------------------------------------------------------------------- #
# Relatório completo
# --------------------------------------------------------------------------- #

def commit_atual(root) -> str | None:
    try:
        from ..app.git_ops import repo_disponivel

        repo = repo_disponivel(Path(root))
        if repo is None or not repo.head.is_valid():
            return None
        return repo.head.commit.hexsha[:12]
    except Exception:  # noqa: BLE001 - qualquer falha = sem git
        return None


def relatorio(ds: Dataset, paths: Paths | None = None, relacoes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rels = relacoes if relacoes is not None else ds.relacoes
    G = construir_grafo(ds, rels)
    nos = metricas_nos(G)
    glob = metricas_grafo(G, ds, rels)
    return {
        "meta": {
            "gerado_em": _dt.datetime.now().isoformat(timespec="seconds"),
            "commit": commit_atual(paths.root) if paths else None,
            "versao_formula": VERSAO_FORMULA,
            "formula": descricao_formula(),
            "seed_comunidades": SEED,
            "n_fontes": len(ds.fontes),
            "n_fontes_processadas": sum(1 for f in ds.fontes if f.get("processado")),
        },
        "global": glob,
        "nos": nos,
        "ranking": {
            chave: ranking(nos, ds, chave)
            for chave in ("grau", "forca", "intermediacao", "proximidade", "autovetor")
        },
        "por_tipo": metricas_por_tipo(ds, rels),
        "auditoria_confianca": auditoria_confianca(rels),
        "convergencia_origens": convergencia_origens(G, ds),
        "proselitismo": proselitismo(ds, rels),
        "temporal": {"cobertura": cobertura_temporal(ds, rels), "decadas": fatias_por_decada(ds, rels)},
        "cobertura": cobertura(ds, G, paths),
        "depoimentos": {
            "n": len(ds.depoimentos),
            "afirmam": sum(1 for d in ds.depoimentos if d.get("existe_escola") is True),
            "negam": sum(1 for d in ds.depoimentos if d.get("existe_escola") is False),
            "indefinidos": sum(1 for d in ds.depoimentos if d.get("existe_escola") is None),
        },
    }
