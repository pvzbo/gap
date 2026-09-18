"""Servidor FastAPI da aplicação interna (``gap triage``).

Rotas HTML: ``/`` (painel de fontes), ``/triagem/{fonte}`` (fila), ``/site/`` (site público).
Rotas JSON: ``/api/...`` documentadas em ``/docs``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import __version__
from ..config import AUTOR_PADRAO, CONFIANCAS, MODELO_EXTRACAO, ROTULOS_TIPO, TIPOS_RELACAO, Paths
from ..ingest.dedup import carregar_decisoes, carregar_fila, montar_fila, relacoes_do_par
from ..store import load_dataset
from . import git_ops
from .actions import Editor, ErroTriagem
from .state import estado_fontes

AQUI = Path(__file__).resolve().parent
paths = Paths()

app = FastAPI(title="GAP — triagem", version=__version__)
templates = Jinja2Templates(directory=str(AQUI / "templates"))
app.mount("/static", StaticFiles(directory=str(AQUI / "static")), name="static")
if paths.site.exists():
    app.mount("/site", StaticFiles(directory=str(paths.site), html=True), name="site")


@app.exception_handler(ErroTriagem)
async def _erro_triagem(_req: Request, exc: ErroTriagem) -> JSONResponse:
    return JSONResponse({"erro": str(exc)}, status_code=400)


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #

@app.get("/", response_class=HTMLResponse)
def painel(request: Request) -> HTMLResponse:
    ds = load_dataset(paths)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "fontes": estado_fontes(paths, ds),
            "git": git_ops.estado(paths.root),
            "n_pessoas": len(ds.pessoas),
            "n_relacoes": len(ds.relacoes),
            "n_depoimentos": len(ds.depoimentos),
            "modelo": MODELO_EXTRACAO,
            "versao": __version__,
        },
    )


@app.get("/triagem", response_class=HTMLResponse)
def triagem_sem_fonte() -> RedirectResponse:
    return RedirectResponse("/triagem/manual")


@app.get("/triagem/{fonte_id}", response_class=HTMLResponse)
def triagem(request: Request, fonte_id: str) -> HTMLResponse:
    ds = load_dataset(paths)
    fonte = ds.fontes_por_id.get(fonte_id)
    if fonte is None and fonte_id != "manual":
        raise HTTPException(404, f"Fonte '{fonte_id}' não existe.")
    return templates.TemplateResponse(
        request,
        "triagem.html",
        {"fonte": fonte or {"id": "manual", "titulo": "Entrada manual", "autor": None, "ano": None}, "fonte_id": fonte_id, "versao": __version__},
    )


# --------------------------------------------------------------------------- #
# API — leitura
# --------------------------------------------------------------------------- #

@app.get("/api/fontes")
def api_fontes() -> list[dict[str, Any]]:
    return estado_fontes(paths, load_dataset(paths))


@app.get("/api/pessoas")
def api_pessoas() -> list[dict[str, Any]]:
    ds = load_dataset(paths)
    return sorted(
        ({"id": p["id"], "nome": p["nome"], "atribuicao": p.get("atribuicao"), "papel": p.get("papel_historiografico"), "aliases": ds.aliases_de(p["id"])} for p in ds.pessoas),
        key=lambda p: p["nome"].lower(),
    )


@app.get("/api/vocabulario")
def api_vocabulario() -> dict[str, Any]:
    ds = load_dataset(paths)
    return {
        "tipos": [{"id": t, "rotulo": ROTULOS_TIPO[t]} for t in TIPOS_RELACAO],
        "confiancas": list(CONFIANCAS),
        "fontes": [{"id": f["id"], "rotulo": f"{f.get('autor') or ''} ({f.get('ano') or 's.d.'}) — {f.get('titulo') or f['id']}".strip()} for f in ds.fontes],
        "instituicoes": [{"id": i["id"], "nome": i.get("nome")} for i in ds.instituicoes],
    }


@app.get("/api/fila/{fonte_id}")
def api_fila(fonte_id: str) -> dict[str, Any]:
    ds = load_dataset(paths)
    itens = carregar_fila(paths, fonte_id) if fonte_id != "manual" else []
    decisoes = carregar_decisoes(paths, fonte_id)
    decididos = {d.get("item_id") for d in decisoes if d.get("item_id")}
    pendentes = [it for it in itens if it["id"] not in decididos]
    adiados = {d["item_id"] for d in decisoes if d.get("acao") == "adiar"}
    # adiados voltam para o fim da fila
    pendentes += [it for it in itens if it["id"] in adiados and it["id"] not in {x["id"] for x in pendentes}]
    return {
        "fonte": fonte_id,
        "n_total": len(itens),
        "n_pendentes": len(pendentes),
        "itens": pendentes,
        "decisoes": list(reversed(decisoes))[:50],
        "placar": {
            "aceitos": sum(1 for d in decisoes if d.get("acao") == "aceitar"),
            "descartados": sum(1 for d in decisoes if d.get("acao") == "descartar"),
            "adiados": sum(1 for d in decisoes if d.get("acao") == "adiar"),
        },
        "git": git_ops.estado(paths.root),
    }


@app.get("/api/par/{a}/{b}")
def api_par(a: str, b: str) -> list[dict[str, Any]]:
    ds = load_dataset(paths)
    return relacoes_do_par(ds, a, b)


@app.get("/api/pessoa/{pid}/relacoes")
def api_relacoes_pessoa(pid: str) -> list[dict[str, Any]]:
    ds = load_dataset(paths)
    out = []
    for r in ds.relacoes:
        if pid in (r["origem"], r["destino"]):
            out.append({**r, "origem_nome": ds.nome(r["origem"]), "destino_nome": ds.nome(r["destino"])})
    return out


# --------------------------------------------------------------------------- #
# API — escrita
# --------------------------------------------------------------------------- #

@app.post("/api/decisao")
def api_decisao(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    fonte_id = payload.get("fonte") or None
    if fonte_id == "manual":
        fonte_id = None
    item_id = payload.get("item_id")
    acao = payload.get("acao")
    categoria = payload.get("categoria") or "relacao"
    dados = payload.get("dados") or {}
    autor = payload.get("autor") or AUTOR_PADRAO
    ed = Editor(paths)
    if acao == "aceitar":
        if categoria == "depoimento":
            return ed.aceitar_depoimento(fonte_id, item_id, dados, autor)
        return ed.aceitar_relacao(fonte_id, item_id, dados, autor)
    if acao in ("descartar", "adiar"):
        if not fonte_id or not item_id:
            raise ErroTriagem("Descartar/adiar exige fonte e item.")
        return ed.registrar_nao_aceite(fonte_id, item_id, acao, payload.get("resumo") or "", payload.get("motivo"), autor)
    raise ErroTriagem(f"Ação desconhecida: {acao}")


@app.post("/api/desfazer/{fonte_id}")
def api_desfazer(fonte_id: str) -> dict[str, Any]:
    return Editor(paths).desfazer(fonte_id)


@app.post("/api/pessoa")
def api_nova_pessoa(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    ed = Editor(paths)
    p = ed.criar_pessoa(payload, payload.get("autor") or AUTOR_PADRAO)
    commit = git_ops.commit(paths.root, f"pessoas: nova pessoa {p['id']}", [paths.pessoas], None)
    return {"pessoa": p, "commit": commit}


@app.post("/api/fonte/{fonte_id}/processado")
def api_processado(fonte_id: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return Editor(paths).marcar_processada(fonte_id, bool(payload.get("valor", True)))


@app.post("/api/pipeline/{fonte_id}/{estagio}")
def api_pipeline(fonte_id: str, estagio: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    ds = load_dataset(paths)
    try:
        if estagio == "chunks":
            from ..ingest.inventory import fonte_para_pdf
            from ..ingest.pdf_to_chunks import processar_pdf

            return processar_pdf(paths, fonte_id, fonte_para_pdf(paths, ds, fonte_id))
        if estagio == "prefilter":
            from ..ingest.prefilter import executar_prefiltro

            st = executar_prefiltro(paths, ds, fonte_id)
            return {k: v for k, v in st.items() if k != "candidatos_por_pagina"}
        if estagio == "extract":
            from ..ingest.extract import extrair_fonte

            return extrair_fonte(
                paths, ds, fonte_id,
                modelo=payload.get("modelo") or MODELO_EXTRACAO,
                limite=payload.get("limite"),
                ids=set(payload["ids"]) if payload.get("ids") else None,
                refazer=bool(payload.get("refazer")),
                dry_run=bool(payload.get("dry_run")),
            )
        if estagio == "queue":
            return montar_fila(paths, ds, fonte_id)
        if estagio == "inventory":
            from ..ingest.inventory import inventariar

            novas = inventariar(paths, ds)
            return {"novas": [f["id"] for f in novas]}
    except (FileNotFoundError, KeyError) as exc:
        raise ErroTriagem(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        nome = type(exc).__name__
        if "Authentication" in nome or "api_key" in str(exc).lower():
            raise ErroTriagem("Sem credencial da API Anthropic: defina ANTHROPIC_API_KEY (ou `ant auth login`) no terminal que roda `gap triage`.") from exc
        raise ErroTriagem(f"{nome}: {exc}") from exc
    raise ErroTriagem(f"Estágio desconhecido: {estagio}")


@app.post("/api/build")
def api_build() -> dict[str, Any]:
    from ..analysis.export import exportar_tudo
    from ..analysis.metrics import relatorio
    from ..validate.ci_checks import resumo, validar

    ds = load_dataset(paths)
    probs = validar(ds, paths)
    erros, avisos = resumo(probs)
    rel = relatorio(ds, paths)
    saidas = exportar_tudo(ds, paths, rel)
    return {
        "erros": erros,
        "avisos": avisos,
        "problemas": [str(p) for p in probs if p.nivel == "erro"][:20],
        "global": {k: rel["global"][k] for k in ("n_pessoas", "n_relacoes", "n_arestas", "n_isolados", "n_componentes", "maior_componente", "modularidade")},
        "saidas": {k: str(v) for k, v in saidas.items()},
    }


@app.get("/api/validar")
def api_validar() -> dict[str, Any]:
    from ..validate.ci_checks import resumo, validar

    ds = load_dataset(paths)
    probs = validar(ds, paths)
    erros, avisos = resumo(probs)
    return {"erros": erros, "avisos": avisos, "problemas": [{"nivel": p.nivel, "regra": p.regra, "entidade": p.entidade, "mensagem": p.mensagem} for p in probs]}
