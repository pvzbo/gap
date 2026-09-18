"""Mutações na base a partir da triagem: aceitar, criar pessoa, mesclar fonte, desfazer.

Cada decisão gera uma linha em ``work/<fonte>/decisoes.jsonl`` com a lista de
``efeitos`` aplicados, o que torna o desfazer determinístico. Paz nunca digita JSON.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..config import AUTOR_PADRAO, TIPOS_RELACAO, Paths
from ..ingest.dedup import encontrar_duplicata, fonte_ja_presente
from ..ingest.lexicon import normalizar
from ..store import Dataset, append_jsonl, hoje, load_dataset, proximo_id, read_jsonl, salvar_aliases, slugify, write_jsonl
from ..validate.schema import Depoimento, Pessoa, Relacao
from . import git_ops


class ErroTriagem(Exception):
    pass


def _limpa(v: Any) -> Any:
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


class Editor:
    def __init__(self, paths: Paths):
        self.paths = paths
        self.ds: Dataset = load_dataset(paths)

    # ------------------------------------------------------------------ util
    def _decisoes_path(self, fonte_id: str) -> Path:
        pasta = self.paths.work_fonte(fonte_id)
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta / "decisoes.jsonl"

    def _gravar_decisao(self, fonte_id: str, decisao: dict[str, Any]) -> None:
        append_jsonl(self._decisoes_path(fonte_id), decisao)

    def _commit(self, mensagem: str, arquivos: list[Path], fonte_id: str | None) -> str | None:
        return git_ops.commit(self.paths.root, mensagem, arquivos, fonte_id)

    # ------------------------------------------------------------------ pessoas
    def criar_pessoa(self, dados: dict[str, Any], autor: str = AUTOR_PADRAO) -> dict[str, Any]:
        nome = _limpa(dados.get("nome"))
        if not nome:
            raise ErroTriagem("Nome da nova pessoa é obrigatório.")
        pid = _limpa(dados.get("id")) or slugify(nome)
        base, n = pid, 2
        ids = {p["id"] for p in self.ds.pessoas}
        while pid in ids:
            pid, n = f"{base}-{n}", n + 1
        pessoa = {
            "id": pid,
            "nome": nome,
            "nome_completo": _limpa(dados.get("nome_completo")),
            "nascimento": dados.get("nascimento") or None,
            "morte": dados.get("morte") or None,
            "local_nascimento": _limpa(dados.get("local_nascimento")),
            "titulo_epoca": _limpa(dados.get("titulo_epoca")),
            "atribuicao": _limpa(dados.get("atribuicao")),
            "papel_historiografico": _limpa(dados.get("papel_historiografico")),
            "formacao": [],
            "atuacao": [],
            "notas": _limpa(dados.get("notas")),
            "status": "rascunho",
            "fontes": [f for f in [_limpa(dados.get("fonte"))] if f],
            "pendencia": _limpa(dados.get("pendencia")) or ("confirmar nome completo em outra fonte" if len(nome.split()) == 1 else None),
            "data_entrada": hoje(),
            "autor_entrada": autor,
        }
        try:
            Pessoa.model_validate(pessoa)
        except ValidationError as exc:
            raise ErroTriagem(f"Pessoa inválida: {exc.errors()[0].get('msg')}") from exc
        append_jsonl(self.paths.pessoas, pessoa)
        self.ds.pessoas.append(pessoa)
        return pessoa

    def registrar_alias(self, pessoa_id: str, variante: str | None) -> bool:
        if not variante or pessoa_id not in self.ds.pessoas_por_id:
            return False
        v = variante.strip()
        p = self.ds.pessoas_por_id[pessoa_id]
        conhecidas = {normalizar(p.get("nome", ""))}
        if p.get("nome_completo"):
            conhecidas.add(normalizar(p["nome_completo"]))
        conhecidas |= {normalizar(x) for x in self.ds.aliases.get(pessoa_id, [])}
        if normalizar(v) in conhecidas or len(v) < 3:
            return False
        self.ds.aliases.setdefault(pessoa_id, []).append(v)
        salvar_aliases(self.paths, self.ds.aliases)
        return True

    def _remover_alias(self, pessoa_id: str, variante: str) -> None:
        lst = self.ds.aliases.get(pessoa_id, [])
        if variante in lst:
            lst.remove(variante)
            if not lst:
                self.ds.aliases.pop(pessoa_id, None)
            salvar_aliases(self.paths, self.ds.aliases)

    # ------------------------------------------------------------------ relações
    def aceitar_relacao(self, fonte_id: str | None, item_id: str | None, dados: dict[str, Any], autor: str = AUTOR_PADRAO) -> dict[str, Any]:
        efeitos: list[dict[str, Any]] = []
        arquivos: list[Path] = []

        # pessoas novas embutidas
        for lado in ("origem", "destino"):
            nova = dados.get(f"nova_{lado}")
            if nova and not dados.get(lado):
                p = self.criar_pessoa({**nova, "fonte": fonte_id}, autor)
                dados[lado] = p["id"]
                efeitos.append({"tipo": "pessoa_nova", "id": p["id"]})
                arquivos.append(self.paths.pessoas)

        origem, destino, tipo = dados.get("origem"), dados.get("destino"), dados.get("tipo")
        if not (origem and destino and tipo):
            raise ErroTriagem("Defina origem, destino e tipo antes de aceitar. Se o texto não permite, use Adiar.")
        if origem == destino:
            raise ErroTriagem("Origem e destino são a mesma pessoa.")
        if tipo not in TIPOS_RELACAO:
            raise ErroTriagem(f"Tipo inválido: {tipo}")
        pessoas = self.ds.pessoas_por_id
        if origem not in pessoas or destino not in pessoas:
            raise ErroTriagem("Origem ou destino não existem na base.")
        if fonte_id and fonte_id not in self.ds.fontes_por_id:
            raise ErroTriagem(f"Fonte '{fonte_id}' não está em fontes.jsonl.")

        confianca = dados.get("confianca") or "documentado"
        fonte_ref = None
        if fonte_id:
            fonte_ref = {"fonte": fonte_id, "pagina": _limpa(str(dados.get("pagina") or "")) or None, "trecho": _limpa(dados.get("trecho"))}
        elif dados.get("fonte_ref"):
            fonte_ref = dados["fonte_ref"]
        pendencia = _limpa(dados.get("pendencia"))
        if confianca == "documentado" and not fonte_ref:
            raise ErroTriagem("Relação documentada exige fonte.")
        if confianca == "hipotese" and not fonte_ref and not pendencia:
            raise ErroTriagem("Hipótese sem fonte exige pendência.")

        simetrico = bool(dados.get("simetrico"))
        dup = encontrar_duplicata(self.ds, origem, destino, tipo, simetrico)
        if dup:
            ja = fonte_ref and fonte_ja_presente(dup, fonte_ref["fonte"])
            mesma_pagina = ja and any(
                f.get("fonte") == fonte_ref["fonte"] and (f.get("pagina") or None) == fonte_ref["pagina"] and (f.get("trecho") or None) == fonte_ref["trecho"]
                for f in dup.get("fontes") or []
            )
            if fonte_ref and not mesma_pagina:
                dup.setdefault("fontes", []).append(fonte_ref)
                efeitos.append({"tipo": "fonte_mesclada", "relacao_id": dup["id"], "fonte_ref": fonte_ref})
            if pendencia and not dup.get("pendencia"):
                dup["pendencia"] = pendencia
            write_jsonl(self.paths.relacoes, self.ds.relacoes)
            arquivos.append(self.paths.relacoes)
            resultado = {"relacao_id": dup["id"], "mesclada": True}
            msg = f"triagem({fonte_id or 'manual'}): reforça {dup['id']} {origem}→{destino} [{tipo}]"
        else:
            rid = proximo_id("rel", (r["id"] for r in self.ds.relacoes))
            rel = {
                "id": rid,
                "origem": origem,
                "destino": destino,
                "tipo": tipo,
                "subtipo": _limpa(dados.get("subtipo")),
                "simetrico": simetrico,
                "periodo": _limpa(dados.get("periodo")),
                "descricao": _limpa(dados.get("descricao")),
                "confianca": confianca,
                "fontes": [fonte_ref] if fonte_ref else [],
                "pendencia": pendencia,
                "rompe": _limpa(dados.get("rompe")),
                "status": "rascunho",
                "data_entrada": hoje(),
                "autor_entrada": autor,
            }
            try:
                Relacao.model_validate(rel)
            except ValidationError as exc:
                raise ErroTriagem(f"Relação inválida: {exc.errors()[0].get('msg')}") from exc
            append_jsonl(self.paths.relacoes, rel)
            self.ds.relacoes.append(rel)
            arquivos.append(self.paths.relacoes)
            efeitos.append({"tipo": "relacao_nova", "id": rid})
            resultado = {"relacao_id": rid, "mesclada": False}
            msg = f"triagem({fonte_id or 'manual'}): {rid} {origem}→{destino} [{tipo}]"

        # aprendizado de variantes
        for lado in ("origem", "destino"):
            variante = _limpa(dados.get(f"{lado}_nome"))
            pid = dados.get(lado)
            if variante and pid and self.registrar_alias(pid, variante):
                efeitos.append({"tipo": "alias_novo", "pessoa": pid, "variante": variante})
                arquivos.append(self.paths.aliases)

        commit = self._commit(msg, arquivos, fonte_id)
        decisao = {
            "quando": _dt.datetime.now().isoformat(timespec="seconds"),
            "fonte": fonte_id,
            "item_id": item_id,
            "acao": "aceitar",
            "categoria": "relacao",
            "resumo": f"{self.ds.nome(origem)} → {self.ds.nome(destino)} · {tipo}",
            "dados": {k: v for k, v in dados.items() if not k.startswith("nova_")},
            "efeitos": efeitos,
            "autor": autor,
            "commit": commit,
        }
        self._gravar_decisao(fonte_id or "manual", decisao)
        return {**resultado, "efeitos": efeitos, "commit": commit, "decisao": decisao}

    # ------------------------------------------------------------------ depoimentos
    def aceitar_depoimento(self, fonte_id: str | None, item_id: str | None, dados: dict[str, Any], autor: str = AUTOR_PADRAO) -> dict[str, Any]:
        efeitos: list[dict[str, Any]] = []
        arquivos: list[Path] = []
        if dados.get("nova_pessoa") and not dados.get("pessoa"):
            p = self.criar_pessoa({**dados["nova_pessoa"], "fonte": fonte_id}, autor)
            dados["pessoa"] = p["id"]
            efeitos.append({"tipo": "pessoa_nova", "id": p["id"]})
            arquivos.append(self.paths.pessoas)
        pessoa = dados.get("pessoa")
        if not pessoa or pessoa not in self.ds.pessoas_por_id:
            raise ErroTriagem("Defina a pessoa do depoimento.")
        if not fonte_id or fonte_id not in self.ds.fontes_por_id:
            raise ErroTriagem("Depoimento exige fonte válida.")
        did = proximo_id("dep", (d["id"] for d in self.ds.depoimentos))
        existe = dados.get("existe_escola")
        if isinstance(existe, str):
            existe = {"true": True, "sim": True, "false": False, "nao": False, "não": False}.get(existe.lower(), None)
        dep = {
            "id": did,
            "pessoa": pessoa,
            "existe_escola": existe,
            "argumento": _limpa(dados.get("argumento")) or "(sem argumento registrado)",
            "fonte": {"fonte": fonte_id, "pagina": _limpa(str(dados.get("pagina") or "")) or None, "trecho": _limpa(dados.get("trecho"))},
            "data_depoimento": _limpa(dados.get("data_depoimento")),
            "status": "rascunho",
            "data_entrada": hoje(),
            "autor_entrada": autor,
        }
        try:
            Depoimento.model_validate(dep)
        except ValidationError as exc:
            raise ErroTriagem(f"Depoimento inválido: {exc.errors()[0].get('msg')}") from exc
        append_jsonl(self.paths.depoimentos, dep)
        self.ds.depoimentos.append(dep)
        arquivos.append(self.paths.depoimentos)
        efeitos.append({"tipo": "depoimento_novo", "id": did})
        variante = _limpa(dados.get("pessoa_nome"))
        if variante and self.registrar_alias(pessoa, variante):
            efeitos.append({"tipo": "alias_novo", "pessoa": pessoa, "variante": variante})
            arquivos.append(self.paths.aliases)
        commit = self._commit(f"triagem({fonte_id}): depoimento {did} de {pessoa}", arquivos, fonte_id)
        decisao = {
            "quando": _dt.datetime.now().isoformat(timespec="seconds"),
            "fonte": fonte_id,
            "item_id": item_id,
            "acao": "aceitar",
            "categoria": "depoimento",
            "resumo": f"{self.ds.nome(pessoa)} · {'afirma' if existe else 'nega' if existe is False else 'indefinido'}",
            "dados": {k: v for k, v in dados.items() if k != "nova_pessoa"},
            "efeitos": efeitos,
            "autor": autor,
            "commit": commit,
        }
        self._gravar_decisao(fonte_id, decisao)
        return {"depoimento_id": did, "efeitos": efeitos, "commit": commit, "decisao": decisao}

    # ------------------------------------------------------------------ descartar / adiar
    def registrar_nao_aceite(self, fonte_id: str, item_id: str, acao: str, resumo: str, motivo: str | None, autor: str = AUTOR_PADRAO) -> dict[str, Any]:
        if acao not in ("descartar", "adiar"):
            raise ErroTriagem(f"Ação inválida: {acao}")
        decisao = {
            "quando": _dt.datetime.now().isoformat(timespec="seconds"),
            "fonte": fonte_id,
            "item_id": item_id,
            "acao": acao,
            "categoria": None,
            "resumo": resumo,
            "motivo": motivo,
            "dados": None,
            "efeitos": [],
            "autor": autor,
            "commit": None,
        }
        self._gravar_decisao(fonte_id, decisao)
        return {"decisao": decisao}

    # ------------------------------------------------------------------ desfazer
    def desfazer(self, fonte_id: str) -> dict[str, Any]:
        path = self._decisoes_path(fonte_id)
        decisoes = read_jsonl(path)
        if not decisoes:
            raise ErroTriagem("Nada a desfazer.")
        ultima = decisoes.pop()
        arquivos: list[Path] = []
        avisos: list[str] = []
        for ef in reversed(ultima.get("efeitos") or []):
            t = ef.get("tipo")
            if t == "relacao_nova":
                self.ds.relacoes = [r for r in self.ds.relacoes if r["id"] != ef["id"]]
                write_jsonl(self.paths.relacoes, self.ds.relacoes)
                arquivos.append(self.paths.relacoes)
            elif t == "fonte_mesclada":
                r = self.ds.relacoes_por_id.get(ef["relacao_id"])
                if r and ef["fonte_ref"] in (r.get("fontes") or []):
                    r["fontes"].remove(ef["fonte_ref"])
                    write_jsonl(self.paths.relacoes, self.ds.relacoes)
                    arquivos.append(self.paths.relacoes)
            elif t == "depoimento_novo":
                self.ds.depoimentos = [d for d in self.ds.depoimentos if d["id"] != ef["id"]]
                write_jsonl(self.paths.depoimentos, self.ds.depoimentos)
                arquivos.append(self.paths.depoimentos)
            elif t == "alias_novo":
                self._remover_alias(ef["pessoa"], ef["variante"])
                arquivos.append(self.paths.aliases)
            elif t == "pessoa_nova":
                em_uso = any(ef["id"] in (r["origem"], r["destino"]) for r in self.ds.relacoes) or any(d["pessoa"] == ef["id"] for d in self.ds.depoimentos)
                if em_uso:
                    avisos.append(f"Pessoa {ef['id']} mantida: ainda referenciada por outra relação/depoimento.")
                else:
                    self.ds.pessoas = [p for p in self.ds.pessoas if p["id"] != ef["id"]]
                    write_jsonl(self.paths.pessoas, self.ds.pessoas)
                    self.ds.aliases.pop(ef["id"], None)
                    salvar_aliases(self.paths, self.ds.aliases)
                    arquivos += [self.paths.pessoas, self.paths.aliases]
        write_jsonl(path, decisoes)
        commit = self._commit(f"triagem({fonte_id}): desfaz {ultima.get('resumo') or ultima.get('item_id')}", arquivos, fonte_id) if arquivos else None
        return {"desfeita": ultima, "avisos": avisos, "commit": commit}

    # ------------------------------------------------------------------ fontes
    def marcar_processada(self, fonte_id: str, valor: bool) -> dict[str, Any]:
        f = self.ds.fontes_por_id.get(fonte_id)
        if not f:
            raise ErroTriagem(f"Fonte '{fonte_id}' não existe.")
        f["processado"] = bool(valor)
        write_jsonl(self.paths.fontes, self.ds.fontes)
        commit = self._commit(f"fontes: {fonte_id} processado={valor}", [self.paths.fontes], fonte_id)
        return {"fonte": f, "commit": commit}
