"""Linha de comando: ``gap <comando>`` (GAP_BRIEF.md §9).

  gap validate                    regras de integridade (CI)
  gap build                       validar → grafo → métricas → exportações → site/data
  gap inventory                   raw_pdfs/ → fontes.jsonl (esqueleto)
  gap chunks <fonte>              estágio 0
  gap prefilter <fonte>           estágio 1
  gap extract <fonte>             estágio 2 (Claude)
  gap queue <fonte>               estágios 3–4 → fila de triagem
  gap ingest <fonte|pdf>          chunks + prefilter (+ extract) + queue
  gap triage                      app interno de triagem (FastAPI)
  gap site                        servir o site público localmente
  gap benchmark <fonte>           comparar funil com o gold standard
  gap status [fonte]              estado do pipeline por fonte
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from . import __version__
from .config import MODELO_EXTRACAO, Paths
from .store import Dataset, load_dataset


def _paths(root: str | None) -> Paths:
    return Paths(Path(root).resolve()) if root else Paths()


def _echo_json(obj) -> None:
    click.echo(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


@click.group(help=__doc__)
@click.version_option(__version__, prog_name="gap")
@click.option("--root", "root", default=None, envvar="GAP_ROOT", help="Raiz do repositório (padrão: pasta do pacote).")
@click.pass_context
def main(ctx: click.Context, root: str | None) -> None:
    ctx.obj = _paths(root)


# --------------------------------------------------------------------------- #
# validate / build
# --------------------------------------------------------------------------- #

@main.command()
@click.option("--avisos/--sem-avisos", default=True, help="Mostrar avisos além dos erros.")
@click.pass_obj
def validate(paths: Paths, avisos: bool) -> None:
    """Valida data/*.jsonl e vocabulários (sai com código 1 se houver erros)."""
    from .validate.ci_checks import resumo, validar_repositorio

    probs = validar_repositorio(paths)
    for p in probs:
        if p.nivel == "erro" or avisos:
            click.echo(str(p))
    erros, n_avisos = resumo(probs)
    click.echo(f"\n{erros} erro(s), {n_avisos} aviso(s).")
    sys.exit(1 if erros else 0)


@main.command()
@click.option("--forcar", is_flag=True, help="Exportar mesmo com erros de validação.")
@click.pass_obj
def build(paths: Paths, forcar: bool) -> None:
    """Regenera export/ e site/data a partir de um checkout limpo."""
    from .analysis.export import exportar_tudo
    from .analysis.metrics import relatorio
    from .validate.ci_checks import resumo, validar

    ds = load_dataset(paths)
    probs = validar(ds, paths)
    erros, n_avisos = resumo(probs)
    for p in probs:
        if p.nivel == "erro":
            click.echo(str(p))
    if erros and not forcar:
        click.echo(f"\n{erros} erro(s) de validação — corrija ou use --forcar.")
        sys.exit(1)
    rel = relatorio(ds, paths)
    saidas = exportar_tudo(ds, paths, rel)
    g = rel["global"]
    click.echo(
        f"pessoas={g['n_pessoas']} relacoes={g['n_relacoes']} arestas={g['n_arestas']} "
        f"isolados={g['n_isolados']} componentes={g['n_componentes']} maior={g['maior_componente']} "
        f"modularidade={g['modularidade']} ({n_avisos} aviso(s) de validação)"
    )
    for nome, p in saidas.items():
        click.echo(f"  {nome:<16} {p}")


# --------------------------------------------------------------------------- #
# inventory
# --------------------------------------------------------------------------- #

@main.command()
@click.option("--dry-run", is_flag=True, help="Só listar, sem gravar em fontes.jsonl.")
@click.pass_obj
def inventory(paths: Paths, dry_run: bool) -> None:
    """Registra em fontes.jsonl os PDFs de raw_pdfs/ ainda não referenciados."""
    from .ingest.inventory import inventariar

    ds = load_dataset(paths)
    novas = inventariar(paths, ds, gravar=not dry_run)
    if not novas:
        click.echo("Nenhum PDF novo.")
        return
    for f in novas:
        click.echo(f"{f['id']:<40} {f['tipo']:<12} {str(f.get('ano') or '?'):<6} {f.get('paginas') or '?':>5} p.  {f['arquivo_local']}")
    click.echo(f"\n{len(novas)} fonte(s) {'listada(s)' if dry_run else 'acrescentada(s)'}. Revise autor/título/ano em data/fontes.jsonl.")


# --------------------------------------------------------------------------- #
# pipeline por fonte
# --------------------------------------------------------------------------- #

def _resolver_fonte(paths: Paths, ds: Dataset, alvo: str) -> tuple[str, Path]:
    from .ingest.inventory import fonte_para_pdf, registrar_pdf_avulso

    p = Path(alvo)
    if p.suffix.lower() == ".pdf" and p.exists():
        rel = None
        try:
            rel = str(p.resolve().relative_to(paths.root.resolve())).replace("\\", "/")
        except ValueError:
            pass
        for f in ds.fontes:
            if f.get("arquivo_local") and (f["arquivo_local"] == rel or Path(f["arquivo_local"]).name == p.name):
                return f["id"], paths.root / f["arquivo_local"] if rel else p
        fonte = registrar_pdf_avulso(paths, ds, p)
        click.echo(f"PDF registrado como fonte '{fonte['id']}' (revise em fontes.jsonl).")
        return fonte["id"], p
    return alvo, fonte_para_pdf(paths, ds, alvo)


@main.command()
@click.argument("fonte")
@click.option("--min-chars", default=40, show_default=True)
@click.pass_obj
def chunks(paths: Paths, fonte: str, min_chars: int) -> None:
    """Estágio 0: PDF → work/<fonte>/chunks.jsonl."""
    from .ingest.pdf_to_chunks import processar_pdf

    ds = load_dataset(paths)
    fid, pdf = _resolver_fonte(paths, ds, fonte)
    meta = processar_pdf(paths, fid, pdf, min_chars=min_chars)
    _echo_json(meta)
    if meta.get("provavel_escaneado"):
        click.echo("ATENÇÃO: pouco texto por página — PDF provavelmente escaneado; requer OCR antes de processar.")


@main.command()
@click.argument("fonte")
@click.pass_obj
def prefilter(paths: Paths, fonte: str) -> None:
    """Estágio 1: pré-filtro léxico → work/<fonte>/candidatos.jsonl."""
    from .ingest.prefilter import executar_prefiltro

    ds = load_dataset(paths)
    stats = executar_prefiltro(paths, ds, fonte)
    resumo = {k: v for k, v in stats.items() if k not in ("gatilhos_mais_frequentes", "pessoas_mais_citadas", "candidatos_por_pagina")}
    _echo_json(resumo)
    click.echo("gatilhos mais frequentes: " + ", ".join(f"{g} ({n})" for g, n in stats["gatilhos_mais_frequentes"][:10]))
    click.echo("pessoas mais citadas: " + ", ".join(f"{ds.nome(p)} ({n})" for p, n in stats["pessoas_mais_citadas"][:10]))


@main.command()
@click.argument("fonte")
@click.option("--modelo", default=MODELO_EXTRACAO, show_default=True, help="Modelo Claude (escalone para claude-sonnet-5 nos ambíguos).")
@click.option("--limite", type=int, default=None, help="Processar só os N candidatos de maior score.")
@click.option("--ids", default=None, help="Lista de chunk_ids separados por vírgula (re-extrai só estes).")
@click.option("--refazer", is_flag=True, help="Ignorar extrações já feitas.")
@click.option("--dry-run", is_flag=True, help="Gerar os prompts sem chamar a API.")
@click.pass_obj
def extract(paths: Paths, fonte: str, modelo: str, limite: int | None, ids: str | None, refazer: bool, dry_run: bool) -> None:
    """Estágio 2: extração estruturada com Claude → work/<fonte>/extraidos.jsonl."""
    from .ingest.extract import extrair_fonte

    ds = load_dataset(paths)
    conj = {s.strip() for s in ids.split(",") if s.strip()} if ids else None

    def prog(i: int, n: int, linha: dict) -> None:
        nr = len(linha.get("relacoes") or [])
        nd = len(linha.get("depoimentos") or [])
        err = " ERRO: " + linha["erro"] if linha.get("erro") else ""
        click.echo(f"[{i}/{n}] {linha['candidato_id']} → {nr} relação(ões), {nd} depoimento(s){err}")

    from .ingest.extract import CredencialAusente, ExtracaoInterrompida

    try:
        stats = extrair_fonte(paths, ds, fonte, modelo=modelo, limite=limite, ids=conj, refazer=refazer, dry_run=dry_run, progresso=prog)
    except CredencialAusente as exc:
        click.echo(f"ERRO: {exc}")
        sys.exit(2)
    except ExtracaoInterrompida as exc:
        click.echo(f"ERRO: {exc}")
        sys.exit(3)
    _echo_json(stats)


@main.command("export-candidatos")
@click.argument("fonte")
@click.option("--limite", type=int, default=None, help="Só os N primeiros candidatos.")
@click.option("--ids", default=None, help="Lista de chunk_ids separados por vírgula.")
@click.option("--pendentes", is_flag=True, help="Só candidatos ainda sem extração (lotes sucessivos sem sobreposição).")
@click.option("--ordem", type=click.Choice(["pagina", "score"]), default="pagina", show_default=True, help="Ordem de leitura ou mais densos primeiro.")
@click.pass_obj
def export_candidatos(paths: Paths, fonte: str, limite: int | None, ids: str | None, pendentes: bool, ordem: str) -> None:
    """Sem chave de API: exporta os candidatos como caderno Markdown + prompts JSONL para leitura humana ou outro modelo."""
    from .ingest.extract import exportar_caderno

    ds = load_dataset(paths)
    conj = {s.strip() for s in ids.split(",") if s.strip()} if ids else None
    st = exportar_caderno(paths, ds, fonte, limite=limite, ids=conj, pendentes=pendentes, ordem=ordem)
    _echo_json({k: v for k, v in st.items() if k != "ids"})
    if st["n_candidatos"] == 0:
        click.echo("Nenhum candidato pendente: a extração desta fonte está completa. Rode `gap queue` e depois `gap triage`.")
        return
    click.echo(f"Leia {st['caderno']} e escreva um JSONL no formato de {Path(st['exemplo']).name}; importe com: "
               f"gap import-extraidos {fonte} <arquivo.jsonl> --modelo <quem-extraiu>")


@main.command("import-extraidos")
@click.argument("fonte")
@click.argument("arquivo", type=click.Path(exists=True, path_type=Path))
@click.option("--modelo", default="manual", show_default=True, help="Rótulo de quem produziu a extração (ex.: claude-code-haiku, leitura-paz).")
@click.option("--permitir-nao-literal", is_flag=True, help="Importar mesmo com trechos que não são cópia literal (a fila exibe alerta).")
@click.pass_obj
def import_extraidos(paths: Paths, fonte: str, arquivo: Path, modelo: str, permitir_nao_literal: bool) -> None:
    """Valida e incorpora um JSONL de extrações produzido fora do pipeline; depois rode `gap queue`."""
    from .ingest.extract import importar_extraidos

    st = importar_extraidos(paths, fonte, arquivo, modelo=modelo, permitir_nao_literal=permitir_nao_literal)
    _echo_json(st)
    if st["invalidos"] or st["candidatos_desconhecidos"]:
        click.echo(f"{len(st['invalidos'])} linha(s) inválida(s) e {len(st['candidatos_desconhecidos'])} candidato_id(s) desconhecido(s) foram ignorados — "
                   "corrija essas linhas no arquivo e importe de novo (as linhas válidas já foram gravadas).")
        sys.exit(1)


@main.command("salvar-extracao")
@click.argument("fonte")
@click.pass_obj
def salvar_extracao_cmd(paths: Paths, fonte: str) -> None:
    """Versiona as propostas de extração em extracoes/<fonte>/ (só trechos curtos; work/ continua fora do Git)."""
    from .ingest.extract import salvar_extracao

    _echo_json(salvar_extracao(paths, fonte))
    click.echo(f"Agora: git add extracoes/{fonte} && git commit")


@main.command("restaurar-extracao")
@click.argument("fonte")
@click.option("--sobrescrever", is_flag=True, help="Substituir linhas já existentes em work/ pelas do repositório.")
@click.pass_obj
def restaurar_extracao_cmd(paths: Paths, fonte: str, sobrescrever: bool) -> None:
    """Traz extracoes/<fonte>/ para work/<fonte>/ (nova máquina ou checkout limpo); depois rode `gap queue`."""
    from .ingest.extract import restaurar_extracao

    _echo_json(restaurar_extracao(paths, fonte, sobrescrever=sobrescrever))


@main.command()
@click.argument("fonte")
@click.pass_obj
def queue(paths: Paths, fonte: str) -> None:
    """Estágios 3–4: resolução de entidades + dedup → work/<fonte>/fila.jsonl."""
    from .ingest.dedup import montar_fila

    ds = load_dataset(paths)
    _echo_json(montar_fila(paths, ds, fonte))


@main.command()
@click.argument("fonte")
@click.option("--extract/--sem-extract", "com_extract", default=False, help="Também rodar a extração com Claude.")
@click.option("--modelo", default=MODELO_EXTRACAO, show_default=True)
@click.option("--limite", type=int, default=None)
@click.pass_obj
def ingest(paths: Paths, fonte: str, com_extract: bool, modelo: str, limite: int | None) -> None:
    """Pipeline completo para uma fonte (ou caminho de PDF)."""
    from .ingest.dedup import montar_fila
    from .ingest.extract import CredencialAusente, ExtracaoInterrompida, credencial_disponivel, extrair_fonte
    from .ingest.pdf_to_chunks import processar_pdf
    from .ingest.prefilter import executar_prefiltro

    if com_extract and not credencial_disponivel():
        from .ingest.extract import MENSAGEM_CREDENCIAL

        click.echo(f"ERRO: {MENSAGEM_CREDENCIAL}")
        sys.exit(2)
    ds = load_dataset(paths)
    fid, pdf = _resolver_fonte(paths, ds, fonte)
    meta = processar_pdf(paths, fid, pdf)
    click.echo(f"[0] chunks: {meta['n_chunks']} em {meta['n_paginas']} páginas" + (" (PROVÁVEL ESCANEADO)" if meta.get("provavel_escaneado") else ""))
    stats = executar_prefiltro(paths, ds, fid)
    click.echo(f"[1] pré-filtro: {stats['n_candidatos']} candidatos ({(stats['taxa_descarte'] or 0) * 100:.1f}% descartados)")
    if com_extract:
        try:
            st = extrair_fonte(paths, ds, fid, modelo=modelo, limite=limite)
        except (CredencialAusente, ExtracaoInterrompida) as exc:
            click.echo(f"ERRO: {exc}")
            sys.exit(2)
        click.echo(f"[2] extração: {st.get('n_processados')} candidatos → {st.get('n_relacoes')} relações, {st.get('n_depoimentos')} depoimentos, {st.get('n_erros')} erros")
        fila = montar_fila(paths, ds, fid)
        click.echo(f"[3-4] fila: {fila['n_itens']} itens ({fila['n_duplicatas']} duplicatas; resolução {fila['resolucao']})")
        click.echo(f"Agora: gap triage --fonte {fid}")
    else:
        click.echo(f"Agora: gap extract {fid}  (ou --dry-run para ver os prompts)")


# --------------------------------------------------------------------------- #
# apps
# --------------------------------------------------------------------------- #

@main.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--porta", default=8765, show_default=True)
@click.option("--fonte", default=None, help="Fonte inicial a triar.")
@click.option("--reload", is_flag=True, help="Recarregar ao editar código (desenvolvimento).")
@click.pass_obj
def triage(paths: Paths, host: str, porta: int, fonte: str | None, reload: bool) -> None:
    """Abre a aplicação interna de triagem (FastAPI)."""
    import os

    import uvicorn

    os.environ["GAP_ROOT"] = str(paths.root)
    url = f"http://{host}:{porta}/" + (f"triagem/{fonte}" if fonte else "")
    if host not in ("127.0.0.1", "localhost", "::1"):
        click.echo(
            "ATENÇÃO: a aplicação de triagem não tem autenticação e grava na base. "
            f"Expor em '{host}' permite que qualquer pessoa na rede edite os dados e dispare chamadas à API Anthropic. "
            "Use 127.0.0.1 ou um túnel autenticado."
        )
    click.echo(f"Triagem em {url}  (Ctrl+C para encerrar)")
    uvicorn.run("gap.app.server:app", host=host, port=porta, reload=reload, log_level="warning")


@main.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--porta", default=8080, show_default=True)
@click.option("--sem-build", is_flag=True, help="Não rodar `gap build` antes.")
@click.pass_obj
def site(paths: Paths, host: str, porta: int, sem_build: bool) -> None:
    """Serve site/ localmente (fetch de data/grafo.json exige HTTP)."""
    import functools
    import http.server

    if not sem_build:
        from .analysis.export import exportar_tudo
        from .analysis.metrics import relatorio

        ds = load_dataset(paths)
        exportar_tudo(ds, paths, relatorio(ds, paths))
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(paths.site))
    click.echo(f"Site em http://{host}:{porta}/  (Ctrl+C para encerrar)")
    with http.server.ThreadingHTTPServer((host, porta), handler) as srv:
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass


# --------------------------------------------------------------------------- #
# benchmark / status
# --------------------------------------------------------------------------- #

@main.command()
@click.argument("fonte")
@click.option("--gold", type=click.Path(path_type=Path), default=None, help="Caminho do relacoes_gold.jsonl.")
@click.option("--detalhes", is_flag=True)
@click.pass_obj
def benchmark(paths: Paths, fonte: str, gold: Path | None, detalhes: bool) -> None:
    """Compara pré-filtro e extração com o gold standard em tests/gold/<fonte>/."""
    from .ingest.benchmark import executar_benchmark

    ds = load_dataset(paths)
    r = executar_benchmark(paths, ds, fonte, gold)
    pf = r["prefiltro"]
    click.echo(f"PRÉ-FILTRO  chunks={pf['n_chunks']} candidatos={pf['n_candidatos']} descarte={(pf['taxa_descarte'] or 0) * 100:.1f}%")
    click.echo(f"            gold documentadas={pf['n_gold_documentadas']} localizáveis no texto={pf['n_localizaveis']} recuperadas={pf['n_recuperadas']}")
    click.echo(f"            recall sobre localizáveis={pf['recall_sobre_localizaveis']}  recall sobre total={pf['recall_sobre_total']}")
    if detalhes:
        for d in pf["detalhes"]:
            flag = "OK " if d["recuperado"] else ("--- " if not d["localizavel"] else "PERDIDA")
            click.echo(f"   {flag:<7} {d['origem']} → {d['destino']} [{d['tipo']}] {d['chunks']}")
    ex = r["extracao"]
    if ex is None:
        click.echo("EXTRAÇÃO    (sem fila.jsonl — rode gap extract + gap queue)")
    else:
        click.echo(f"EXTRAÇÃO    propostas={ex['n_propostas']} recall(par+tipo)={ex['recall_par_e_tipo']} recall(par)={ex['recall_par']} falsos={ex['taxa_falsos']}")
        click.echo(f"            meta recall≥0.8: {ex['meta_recall_atingida']}  meta falsos≤0.2: {ex['meta_falsos_atingida']}")
        if detalhes and ex["nao_recuperadas"]:
            for d in ex["nao_recuperadas"]:
                click.echo(f"   PERDIDA {d['origem']} → {d['destino']} [{d['tipo']}]")


@main.command()
@click.argument("fonte", required=False)
@click.pass_obj
def status(paths: Paths, fonte: str | None) -> None:
    """Estado do pipeline (chunks / candidatos / extraídos / fila / decisões) por fonte."""
    from .app.state import estado_fontes

    ds = load_dataset(paths)
    linhas = estado_fontes(paths, ds)
    if fonte:
        linhas = [l for l in linhas if l["id"] == fonte]
    click.echo(f"{'fonte':<36} {'pdf':>3} {'chunks':>7} {'cand.':>6} {'extr.':>6} {'pend.':>6} {'fila':>5} {'decid.':>6} {'proc.':>5}")
    for l in linhas:
        click.echo(
            f"{l['id']:<36} {'sim' if l['tem_pdf'] else '—':>3} {l['n_chunks'] if l['n_chunks'] is not None else '—':>7} "
            f"{l['n_candidatos'] if l['n_candidatos'] is not None else '—':>6} {l['n_extraidos'] if l['n_extraidos'] is not None else '—':>6} "
            f"{l['n_extr_pendentes'] if l.get('n_extr_pendentes') is not None else '—':>6} "
            f"{l['n_fila'] if l['n_fila'] is not None else '—':>5} {l['n_decisoes'] if l['n_decisoes'] is not None else '—':>6} {'sim' if l['processado'] else '—':>5}"
        )


if __name__ == "__main__":  # pragma: no cover
    main()
