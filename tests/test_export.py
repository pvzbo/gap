import json

from gap.analysis.export import exportar_tudo
from gap.analysis.metrics import relatorio
from gap.store import load_dataset


def test_exportar_tudo(repo_tmp):
    ds = load_dataset(repo_tmp)
    saidas = exportar_tudo(ds, repo_tmp, relatorio(ds, repo_tmp))
    esperados = {"grafo.json", "metricas.json", "metricas.md", "pendencias.md", "pessoas.csv", "relacoes.csv", "grafo.gexf", "grafo.graphml"}
    assert esperados <= set(saidas)
    for p in saidas.values():
        assert p.exists() and p.stat().st_size > 0
    grafo = json.loads(saidas["grafo.json"].read_text(encoding="utf-8"))
    assert len(grafo["pessoas"]) == 26 and len(grafo["arestas"]) == 26
    assert grafo["tipos"]["estudo"]["cor"] == "#4A6B4F"
    assert (repo_tmp.site_data / "grafo.json").exists()
    linhas = saidas["pessoas.csv"].read_text(encoding="utf-8-sig").splitlines()
    assert len(linhas) == 27
    assert linhas[0].startswith("id,nome,")
    md = saidas["metricas.md"].read_text(encoding="utf-8")
    assert "Auditoria de confiança" in md and "Convergência de origens" in md
