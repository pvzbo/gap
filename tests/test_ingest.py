import pytest

from gap.ingest.dedup import chave_relacao, encontrar_duplicata
from gap.ingest.extract import CredencialAusente, ExtracaoInterrompida, credencial_disponivel, extrair_fonte
from gap.ingest.lexicon import Gazetteer, Lexico, nomes_desconhecidos, normalizar
from gap.store import read_jsonl, write_jsonl
from gap.ingest.pdf_to_chunks import limpar_texto
from gap.ingest.prefilter import prefiltrar
from gap.ingest.resolve import Resolvedor, limpar_nome


def test_normalizar():
    assert normalizar("Maurício  do Passo  CASTRO") == "mauricio do passo castro"


def test_limpar_texto_hifenacao():
    assert limpar_texto("a arquite-\ntura moderna\nem Recife") == "a arquitetura moderna em Recife"


def test_lexico_detecta_gatilhos(paths_repo):
    lex = Lexico.carregar(paths_repo.lexico)
    g = lex.gatilhos(normalizar("Havendo sido aluno de Russo, tornou-se sócio de Castro em 1964."))
    grupos = {x.grupo for x in g}
    assert {"estudo", "societario"} <= grupos


def test_gazetteer_reconhece_variantes(ds_repo):
    gaz = Gazetteer.do_dataset(ds_repo)
    achados = gaz.nomes(normalizar("Ainda estudante foi convidado por Mario Russo; Russo o levou ao ETCUR."))
    ids = {a.pessoa_id for a in achados}
    assert ids == {"mario-russo"}
    assert any(a.tokens == 2 for a in achados) and any(a.tokens == 1 for a in achados)


def test_nomes_desconhecidos_ignora_instituicoes(ds_repo):
    gaz = Gazetteer.do_dataset(ds_repo)
    nomes = nomes_desconhecidos("Trabalhou com Joaquim Cardozo na Escola de Belas Artes de Pernambuco e com Mario Russo.", gaz)
    assert nomes == ["Joaquim Cardozo"]


def test_prefiltro_exige_nome_e_gatilho(ds_repo, paths_repo):
    gaz = Gazetteer.do_dataset(ds_repo)
    lex = Lexico.carregar(paths_repo.lexico)
    chunks = [
        {"chunk_id": "t-p0001-b001", "pagina": 1, "paragrafo": 1, "texto": "Mario Russo nasceu em 1917 e chegou ao Recife em 1949."},
        {"chunk_id": "t-p0001-b002", "pagina": 1, "paragrafo": 2, "texto": "Ainda estudante foi convidado por Mario Russo para trabalhar no ETCUR."},
        {"chunk_id": "t-p0001-b003", "pagina": 1, "paragrafo": 3, "texto": "A cidade cresceu rapidamente e novos bairros surgiram, sem que ninguém fosse sócio de ninguém."},
    ]
    cands, stats = prefiltrar(chunks, gaz, lex)
    assert [c.chunk_id for c in cands] == ["t-p0001-b002"]
    assert cands[0].contexto_anterior.startswith("Mario Russo nasceu")
    assert "mestre-aprendiz" in cands[0].tipos_sugeridos
    assert stats["n_com_nome_sem_gatilho"] == 1 and stats["n_com_gatilho_sem_nome"] == 1


def test_limpar_nome():
    assert limpar_nome("o arquiteto Reginaldo Esteves,") == "Reginaldo Esteves"
    assert limpar_nome("professor italiano Mario Russo") == "Mario Russo"


def test_resolvedor(ds_repo):
    res = Resolvedor(ds_repo)
    assert res.resolver("Maurício Castro").decisao == "auto" and res.resolver("Maurício Castro").id == "mauricio-castro"
    assert res.resolver("o arquiteto Reginaldo Esteves").id == "reginaldo-esteves"
    r = res.resolver("Castro")
    assert r.decisao == "humano" and r.id == "mauricio-castro"
    r = res.resolver("Joaquim Cardozo")
    assert r.decisao == "novo" and r.id is None and r.id_provisorio == "joaquim-cardozo"
    assert res.resolver("Heitor Maia").id == "heitor-maia-neto"
    assert res.resolver("Waldecy Fernandes Pinto").id == "waldeci-pinto"


def _candidatos_falsos(paths, n=5):
    pasta = paths.work_fonte("afonso-2008")
    pasta.mkdir(parents=True, exist_ok=True)
    write_jsonl(pasta / "candidatos.jsonl", (
        {"chunk_id": f"afonso-2008-p0001-b{i:03d}", "pagina": 1, "paragrafo": i, "texto": f"texto {i}", "contexto_anterior": "", "contexto_posterior": "",
         "nomes_conhecidos": [], "nomes_desconhecidos": [], "gatilhos": [], "tipos_sugeridos": [], "eh_depoimento": False, "score": 1.0}
        for i in range(1, n + 1)
    ))
    return pasta


def test_extracao_sem_credencial_aborta_antes_de_chamar(repo_tmp, monkeypatch, tmp_path):
    from gap.store import load_dataset

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(tmp_path / "sem-perfil"))
    assert not credencial_disponivel()
    pasta = _candidatos_falsos(repo_tmp)
    with pytest.raises(CredencialAusente):
        extrair_fonte(repo_tmp, load_dataset(repo_tmp), "afonso-2008")
    assert not (pasta / "extraidos.jsonl").exists()


def test_extracao_interrompe_apos_falhas_consecutivas(repo_tmp, monkeypatch):
    from gap.ingest import extract as ex
    from gap.store import load_dataset

    pasta = _candidatos_falsos(repo_tmp)

    def falha(*_a, **_k):
        raise ValueError("resposta sem JSON")

    monkeypatch.setattr(ex, "chamar_modelo", falha)
    with pytest.raises(ExtracaoInterrompida):
        ex.extrair_fonte(repo_tmp, load_dataset(repo_tmp), "afonso-2008", client=object())
    linhas = read_jsonl(pasta / "extraidos.jsonl")
    assert len(linhas) == ex.MAX_FALHAS_CONSECUTIVAS and all(l.get("erro") for l in linhas)

    # erro de credencial no meio da execução não é persistido
    def falha_auth(*_a, **_k):
        raise TypeError("Could not resolve authentication method. Expected one of api_key, auth_token...")

    monkeypatch.setattr(ex, "chamar_modelo", falha_auth)
    with pytest.raises(CredencialAusente):
        ex.extrair_fonte(repo_tmp, load_dataset(repo_tmp), "afonso-2008", client=object(), refazer=True)
    assert len(read_jsonl(pasta / "extraidos.jsonl")) == ex.MAX_FALHAS_CONSECUTIVAS


def test_dedup_chave_e_busca(ds_repo):
    assert chave_relacao("b", "a", "societario", True) == ("a", "b", "societario")
    assert chave_relacao("b", "a", "estudo", False) == ("b", "a", "estudo")
    d = encontrar_duplicata(ds_repo, "reginaldo-esteves", "mauricio-castro", "societario", True)
    assert d and d["id"] == "rel-0020"
    assert encontrar_duplicata(ds_repo, "mauricio-castro", "mario-russo", "estudo", False) is None
    assert encontrar_duplicata(ds_repo, "mario-russo", "mauricio-castro", "estudo", False)["id"] == "rel-0001"
