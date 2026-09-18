import pytest

from gap.ingest.benchmark import executar_benchmark


def test_benchmark_prefiltro_afonso(ds_repo, paths_repo):
    """Só roda quando o funil já foi executado localmente (work/ não é versionado)."""
    pasta = paths_repo.work_fonte("afonso-2008")
    if not (pasta / "candidatos.jsonl").exists():
        pytest.skip("rode `gap chunks afonso-2008` e `gap prefilter afonso-2008` primeiro")
    r = executar_benchmark(paths_repo, ds_repo, "afonso-2008")
    pf = r["prefiltro"]
    assert pf["n_gold_documentadas"] == 29
    assert pf["recall_sobre_localizaveis"] >= 0.8
