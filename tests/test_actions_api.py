import importlib

import pytest

from gap.app.actions import Editor, ErroTriagem
from gap.store import load_dataset, read_jsonl


def test_aceitar_nova_relacao_e_desfazer(repo_tmp):
    ed = Editor(repo_tmp)
    r = ed.aceitar_relacao("afonso-2008", "item-1", {
        "origem": "luiz-nunes", "destino": "airton-carvalho", "tipo": "trabalho", "confianca": "hipotese",
        "pagina": "2", "trecho": "frase de teste", "pendencia": "verificar", "origem_nome": "Luís Nunes de Barros",
    })
    assert r["relacao_id"] == "rel-0033" and not r["mesclada"]
    rels = read_jsonl(repo_tmp.relacoes)
    assert rels[-1]["id"] == "rel-0033" and rels[-1]["fontes"][0]["pagina"] == "2"
    assert any(e["tipo"] == "alias_novo" for e in r["efeitos"])
    assert "Luís Nunes de Barros" in load_dataset(repo_tmp).aliases["luiz-nunes"]

    u = ed.desfazer("afonso-2008")
    assert u["desfeita"]["item_id"] == "item-1"
    assert len(read_jsonl(repo_tmp.relacoes)) == 32
    assert "Luís Nunes de Barros" not in load_dataset(repo_tmp).aliases.get("luiz-nunes", [])
    assert read_jsonl(repo_tmp.work_fonte("afonso-2008") / "decisoes.jsonl") == []


def test_aceitar_duplicata_mescla_fonte(repo_tmp):
    ed = Editor(repo_tmp)
    r = ed.aceitar_relacao("porto-2021", "item-2", {
        "origem": "mauricio-castro", "destino": "reginaldo-esteves", "tipo": "societario", "simetrico": True,
        "confianca": "documentado", "pagina": "77", "trecho": "outra frase",
    })
    assert r["mesclada"] and r["relacao_id"] == "rel-0020"
    rel = next(x for x in read_jsonl(repo_tmp.relacoes) if x["id"] == "rel-0020")
    assert [f["fonte"] for f in rel["fontes"]] == ["afonso-2008", "porto-2021"]
    ed.desfazer("porto-2021")
    rel = next(x for x in read_jsonl(repo_tmp.relacoes) if x["id"] == "rel-0020")
    assert [f["fonte"] for f in rel["fontes"]] == ["afonso-2008"]


def test_aceitar_com_pessoa_nova(repo_tmp):
    ed = Editor(repo_tmp)
    r = ed.aceitar_relacao("afonso-2008", "item-3", {
        "origem": "luiz-nunes", "nova_destino": {"nome": "Joaquim Cardozo", "atribuicao": "engenheiro"},
        "tipo": "trabalho", "confianca": "documentado", "pagina": "3", "trecho": "trecho",
    })
    assert r["relacao_id"] == "rel-0033"
    ds = load_dataset(repo_tmp)
    assert "joaquim-cardozo" in ds.pessoas_por_id
    ed.desfazer("afonso-2008")
    assert "joaquim-cardozo" not in load_dataset(repo_tmp).pessoas_por_id


def test_regras_de_evidencia_na_triagem(repo_tmp):
    ed = Editor(repo_tmp)
    with pytest.raises(ErroTriagem):
        ed.aceitar_relacao(None, None, {"origem": "luiz-nunes", "destino": "airton-carvalho", "tipo": "trabalho", "confianca": "documentado"})
    with pytest.raises(ErroTriagem):
        ed.aceitar_relacao("afonso-2008", "x", {"origem": "luiz-nunes", "destino": "luiz-nunes", "tipo": "trabalho", "pagina": "1"})


def test_depoimento(repo_tmp):
    ed = Editor(repo_tmp)
    r = ed.aceitar_depoimento("afonso-2008", "d-1", {"pessoa": "heitor-maia-neto", "existe_escola": "false", "argumento": "teste", "trecho": "t", "pagina": "1"})
    assert r["depoimento_id"] == "dep-0006"
    ed.desfazer("afonso-2008")
    assert len(read_jsonl(repo_tmp.depoimentos)) == 5


def test_api(repo_tmp, monkeypatch):
    monkeypatch.setenv("GAP_ROOT", str(repo_tmp.root))
    import gap.app.server as server

    importlib.reload(server)
    from fastapi.testclient import TestClient

    c = TestClient(server.app)
    assert c.get("/").status_code == 200
    assert c.get("/triagem/afonso-2008").status_code == 200
    assert c.get("/triagem/manual").status_code == 200
    assert len(c.get("/api/pessoas").json()) == 26
    assert c.get("/api/fila/afonso-2008").json()["n_total"] == 0
    r = c.post("/api/decisao", json={"fonte": "afonso-2008", "item_id": "i1", "acao": "aceitar", "categoria": "relacao", "dados": {
        "origem": "luiz-nunes", "destino": "airton-carvalho", "tipo": "trabalho", "confianca": "hipotese", "pagina": "1", "trecho": "x", "pendencia": "p"}})
    assert r.status_code == 200 and r.json()["relacao_id"] == "rel-0033"
    assert c.post("/api/desfazer/afonso-2008").status_code == 200
    r = c.post("/api/decisao", json={"fonte": "afonso-2008", "item_id": "i2", "acao": "aceitar", "dados": {"origem": "luiz-nunes", "destino": "", "tipo": "trabalho"}})
    assert r.status_code == 400 and "origem, destino e tipo" in r.json()["erro"]
    assert c.post("/api/build").json()["erros"] == 0
    assert c.get("/api/validar").json()["erros"] == 0
