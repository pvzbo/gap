import json

import pytest

from gap.analysis.graph import componentes, construir_grafo, ego, sem_isolados
from gap.analysis.metrics import relatorio
from gap.analysis.temporal import fatias_por_decada, parse_periodo
from gap.analysis.weights import peso_aresta, peso_relacao


def test_peso_formula():
    assert peso_relacao({"confianca": "documentado", "fontes": [{"fonte": "a"}]}) == 1.0
    assert peso_relacao({"confianca": "documentado", "fontes": [{"fonte": "a"}, {"fonte": "b"}]}) == 1.5
    assert peso_relacao({"confianca": "documentado", "fontes": [{"fonte": "a"}, {"fonte": "a", "pagina": "2"}]}) == 1.0
    assert peso_relacao({"confianca": "tradicao_oral", "fontes": [{"fonte": "a"}]}) == 0.6
    assert peso_relacao({"confianca": "hipotese", "fontes": []}) == pytest.approx(0.15)
    assert peso_aresta([{"confianca": "documentado", "fontes": [{"fonte": "a"}]}, {"confianca": "hipotese", "fontes": [{"fonte": "a"}]}]) == pytest.approx(1.3)


def test_grafo_semente_colapsa_relacoes_em_arestas(ds_repo):
    G = construir_grafo(ds_repo)
    assert G.number_of_nodes() == len(ds_repo.pessoas) == 26
    assert len(ds_repo.relacoes) == 32
    assert G.number_of_edges() == 26
    # Castro–Esteves: estudo? não — societario apenas; Russo–Castro: estudo + mestre-aprendiz
    e = G["mario-russo"]["mauricio-castro"]
    assert e["tipos"] == ["mestre-aprendiz", "estudo"]
    assert e["n_relacoes"] == 2
    assert e["peso"] == pytest.approx(2.0)


def test_sem_hipoteses_reproduz_simulacao_do_brief(ds_repo):
    G = sem_isolados(construir_grafo(ds_repo, incluir_hipoteses=False))
    tamanhos = [len(c) for c in componentes(G)]
    assert tamanhos == [17, 2]  # núcleo + Paulo Vaz & Burle Ferreira
    G_full = construir_grafo(ds_repo, incluir_hipoteses=False)
    assert sum(1 for _, d in G_full.degree() if d == 0) == 7


def test_ego(ds_repo):
    E = ego(construir_grafo(ds_repo), "mauricio-castro", 1)
    assert {"heitor-maia-neto", "helio-maia", "reginaldo-esteves", "mario-russo"} <= set(E.nodes)


def test_relatorio_completo_e_serializavel(ds_repo, paths_repo):
    rel = relatorio(ds_repo, paths_repo)
    json.dumps(rel)
    g = rel["global"]
    assert g["n_pessoas"] == 26 and g["n_relacoes"] == 32 and g["n_arestas"] == 26
    assert g["modularidade"] is not None
    top_inter = [r["id"] for r in rel["ranking"]["intermediacao"][:3]]
    assert "waldeci-pinto" in top_inter and "reginaldo-esteves" in top_inter
    assert "luiz-nunes" in rel["convergencia_origens"]["presentes_isoladas"]
    assert rel["auditoria_confianca"]["por_tipo"]["estudo"]["hipotese"] == 3
    assert rel["proselitismo"]["n_relacoes_ensino"] == 20  # 15 estudo + 5 mestre-aprendiz
    assert rel["cobertura"]["n_isolados"] == 5


def test_parse_periodo():
    assert parse_periodo("1950-1954") == (1950, 1954)
    assert parse_periodo("1954-") == (1954, None)
    assert parse_periodo("1958") == (1958, 1958)
    assert parse_periodo("-1937") == (None, 1937)
    assert parse_periodo("anos 1950") == (1950, 1959)
    assert parse_periodo("c. 1960") == (1960, 1960)
    assert parse_periodo("século XX") is None
    assert parse_periodo(None) is None


def test_fatias_por_decada(ds_repo):
    fat = fatias_por_decada(ds_repo)
    assert [f["decada"] for f in fat] == [1940, 1950, 1960]
    assert fat[-1]["acumulado"]["n_relacoes"] >= fat[-1]["fatia"]["n_relacoes"]
