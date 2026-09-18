import copy

import pytest
from pydantic import ValidationError

from gap.store import Dataset
from gap.validate import Pessoa, Relacao, validar
from gap.validate.ci_checks import resumo


def test_seed_valida_sem_erros(ds_repo, paths_repo):
    probs = validar(ds_repo, paths_repo)
    erros, _ = resumo(probs)
    assert erros == 0, [str(p) for p in probs if p.nivel == "erro"]


def test_seed_avisa_nome_incompleto(ds_repo, paths_repo):
    probs = validar(ds_repo, paths_repo)
    assert any(p.regra == "nome-incompleto" and "didier" in p.entidade for p in probs)


def test_schema_rejeita_campo_desconhecido():
    with pytest.raises(ValidationError):
        Pessoa.model_validate({"id": "x-y", "nome": "X Y", "peso": 3})


def test_schema_rejeita_tipo_invalido():
    with pytest.raises(ValidationError):
        Relacao.model_validate({"id": "rel-0001", "origem": "a-b", "destino": "c-d", "tipo": "influencia", "confianca": "documentado"})


def test_schema_rejeita_auto_relacao():
    with pytest.raises(ValidationError):
        Relacao.model_validate({"id": "rel-0001", "origem": "a-b", "destino": "a-b", "tipo": "estudo", "confianca": "documentado"})


def _clone(ds: Dataset) -> Dataset:
    return Dataset(
        pessoas=copy.deepcopy(ds.pessoas), relacoes=copy.deepcopy(ds.relacoes), depoimentos=copy.deepcopy(ds.depoimentos),
        fontes=copy.deepcopy(ds.fontes), instituicoes=copy.deepcopy(ds.instituicoes), aliases=copy.deepcopy(ds.aliases),
    )


def test_duplicata_par_tipo_e_erro(ds_repo):
    ds = _clone(ds_repo)
    dup = copy.deepcopy(ds.relacoes[0])
    dup["id"] = "rel-9999"
    ds.relacoes.append(dup)
    assert any(p.regra == "duplicata" for p in validar(ds))


def test_duplicata_simetrica_ignora_ordem(ds_repo):
    ds = _clone(ds_repo)
    r = copy.deepcopy(next(x for x in ds.relacoes if x["tipo"] == "societario"))
    r["id"] = "rel-9998"
    r["origem"], r["destino"] = r["destino"], r["origem"]
    ds.relacoes.append(r)
    assert any(p.regra == "duplicata" for p in validar(ds))


def test_documentado_sem_fonte_e_erro(ds_repo):
    ds = _clone(ds_repo)
    ds.relacoes[0]["fontes"] = []
    assert any(p.regra == "evidencia" for p in validar(ds))


def test_hipotese_sem_fonte_exige_pendencia(ds_repo):
    ds = _clone(ds_repo)
    r = next(x for x in ds.relacoes if x["confianca"] == "hipotese")
    r["fontes"] = []
    r["pendencia"] = None
    assert any(p.regra == "evidencia" for p in validar(ds))


def test_instituicao_fora_do_vocabulario_e_erro(ds_repo):
    ds = _clone(ds_repo)
    ds.pessoas[1]["atuacao"].append({"tipo": "escola", "nome": "ESCOLA-INEXISTENTE", "papel": None, "periodo": None})
    assert any(p.regra == "instituicao" for p in validar(ds))


def test_referencia_quebrada_e_erro(ds_repo):
    ds = _clone(ds_repo)
    ds.relacoes[0]["destino"] = "pessoa-que-nao-existe"
    assert any(p.regra == "referencia" for p in validar(ds))
