from gap.ingest.dedup import chave_relacao, encontrar_duplicata
from gap.ingest.lexicon import Gazetteer, Lexico, nomes_desconhecidos, normalizar
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


def test_dedup_chave_e_busca(ds_repo):
    assert chave_relacao("b", "a", "societario", True) == ("a", "b", "societario")
    assert chave_relacao("b", "a", "estudo", False) == ("b", "a", "estudo")
    d = encontrar_duplicata(ds_repo, "reginaldo-esteves", "mauricio-castro", "societario", True)
    assert d and d["id"] == "rel-0020"
    assert encontrar_duplicata(ds_repo, "mauricio-castro", "mario-russo", "estudo", False) is None
    assert encontrar_duplicata(ds_repo, "mario-russo", "mauricio-castro", "estudo", False)["id"] == "rel-0001"
