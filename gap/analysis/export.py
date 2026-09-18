"""Exportações regeneradas a cada build (GAP_BRIEF.md §6.5).

- export/grafo.json      — nós + arestas + métricas, consumido pelo site
- export/pessoas.csv     — todos os nomes com ids, atribuição, datas, grau, força, comunidade
- export/relacoes.csv    — tabela plana de relações com fontes
- export/metricas.json   — relatório completo
- export/metricas.md     — relatório legível (apêndice reproduzível)
- export/grafo.gexf      — para Gephi
- export/grafo.graphml   — para outras ferramentas
- export/pendencias.md   — agenda de pesquisa
"""
from __future__ import annotations

import csv
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import networkx as nx

from .. import __version__
from ..config import (
    CORES_PAPEL,
    CORES_TIPO,
    ORIGENS_CANONICAS,
    ROTULOS_CONFIANCA,
    ROTULOS_PAPEL,
    ROTULOS_TIPO,
    TIPOS_RELACAO,
    Paths,
)
from ..store import Dataset, write_json
from .graph import construir_grafo
from .metrics import relatorio as _relatorio
from .temporal import eventos_pessoa


# --------------------------------------------------------------------------- #
# grafo.json
# --------------------------------------------------------------------------- #

def montar_grafo_json(ds: Dataset, G: nx.Graph, rel: dict[str, Any]) -> dict[str, Any]:
    nos_m = rel["nos"]
    deps = defaultdict(list)
    for d in ds.depoimentos:
        deps[d["pessoa"]].append(d)
    rel_por_pessoa: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in ds.relacoes:
        rel_por_pessoa[r["origem"]].append(r)
        rel_por_pessoa[r["destino"]].append(r)

    pessoas = []
    for p in ds.pessoas:
        pid = p["id"]
        pessoas.append(
            {
                "id": pid,
                "nome": p.get("nome"),
                "nome_completo": p.get("nome_completo"),
                "nascimento": p.get("nascimento"),
                "morte": p.get("morte"),
                "local_nascimento": p.get("local_nascimento"),
                "titulo_epoca": p.get("titulo_epoca"),
                "atribuicao": p.get("atribuicao"),
                "papel": p.get("papel_historiografico") or "outro",
                "status": p.get("status"),
                "formacao": p.get("formacao") or [],
                "atuacao": p.get("atuacao") or [],
                "notas": p.get("notas"),
                "pendencia": p.get("pendencia"),
                "fontes": p.get("fontes") or [],
                "aliases": ds.aliases_de(pid),
                "metricas": nos_m.get(pid, {}),
                "depoimentos": deps.get(pid, []),
                "relacoes": [r["id"] for r in rel_por_pessoa.get(pid, [])],
                "eventos": eventos_pessoa(p, rel_por_pessoa.get(pid, []), ds),
            }
        )

    rels_por_id = ds.relacoes_por_id
    arestas = []
    for a, b, d in G.edges(data=True):
        arestas.append(
            {
                "source": a,
                "target": b,
                "peso": d["peso"],
                "tipos": d["tipos"],
                "tipo_dominante": d["tipo_dominante"],
                "confiancas": d["confiancas"],
                "apenas_hipotese": d["apenas_hipotese"],
                "n_relacoes": d["n_relacoes"],
                "n_fontes": d["n_fontes"],
                "relacoes": [rels_por_id[i] for i in d["relacoes"] if i in rels_por_id],
            }
        )
    arestas.sort(key=lambda e: (e["source"], e["target"]))

    membros_inst: dict[str, set[str]] = defaultdict(set)
    for p in ds.pessoas:
        for a in p.get("atuacao") or []:
            membros_inst[a.get("nome")].add(p["id"])
        for f in p.get("formacao") or []:
            membros_inst[f.get("instituicao")].add(p["id"])
    instituicoes = [
        {
            "id": i["id"],
            "nome": i.get("nome"),
            "tipo": i.get("tipo"),
            "cidade": i.get("cidade"),
            "periodo": i.get("periodo"),
            "membros": sorted(membros_inst.get(i["id"], set())),
        }
        for i in ds.instituicoes
    ]
    instituicoes.sort(key=lambda i: (-len(i["membros"]), i["nome"] or ""))

    fontes = {
        f["id"]: {k: f.get(k) for k in ("id", "tipo", "autor", "titulo", "veiculo", "ano", "url", "processado")}
        for f in ds.fontes
    }

    return {
        "meta": {
            **rel["meta"],
            "versao_gap": __version__,
            "n_pessoas": len(ds.pessoas),
            "n_relacoes": len(ds.relacoes),
            "n_arestas": G.number_of_edges(),
            "n_depoimentos": len(ds.depoimentos),
            "origens_canonicas": list(ORIGENS_CANONICAS),
        },
        "tipos": {t: {"rotulo": ROTULOS_TIPO[t], "cor": CORES_TIPO[t]} for t in TIPOS_RELACAO},
        "papeis": {p: {"rotulo": ROTULOS_PAPEL[p], "cor": CORES_PAPEL[p]} for p in ROTULOS_PAPEL},
        "confiancas": ROTULOS_CONFIANCA,
        "pessoas": pessoas,
        "arestas": arestas,
        "fontes": fontes,
        "instituicoes": instituicoes,
        "metricas_globais": rel["global"],
        "ranking": rel["ranking"],
        "por_tipo": rel["por_tipo"],
        "auditoria_confianca": rel["auditoria_confianca"],
        "convergencia_origens": rel["convergencia_origens"],
        "proselitismo": rel["proselitismo"],
        "temporal": rel["temporal"],
        "cobertura": rel["cobertura"],
        "depoimentos_resumo": rel["depoimentos"],
    }


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #

def _csv(path: Path, cabecalho: list[str], linhas: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cabecalho)
        for ln in linhas:
            w.writerow(["" if v is None else v for v in ln])


def exportar_pessoas_csv(ds: Dataset, rel: dict[str, Any], path: Path) -> None:
    nos = rel["nos"]
    origens = [o for o in ORIGENS_CANONICAS]
    cab = [
        "id", "nome", "nome_completo", "atribuicao", "papel_historiografico", "nascimento", "morte",
        "local_nascimento", "status", "n_relacoes", "grau", "forca", "intermediacao", "proximidade",
        "autovetor", "componente", "tamanho_componente", "comunidade", "isolado",
    ] + [f"saltos_{o}" for o in origens] + ["instituicoes", "aliases", "fontes", "pendencia"]
    n_rel = defaultdict(int)
    for r in ds.relacoes:
        n_rel[r["origem"]] += 1
        n_rel[r["destino"]] += 1
    linhas = []
    for p in sorted(ds.pessoas, key=lambda x: x.get("nome", "")):
        m = nos.get(p["id"], {})
        inst = sorted({a.get("nome") for a in p.get("atuacao") or []} | {f.get("instituicao") for f in p.get("formacao") or []})
        linhas.append(
            [
                p["id"], p.get("nome"), p.get("nome_completo"), p.get("atribuicao"), p.get("papel_historiografico"),
                p.get("nascimento"), p.get("morte"), p.get("local_nascimento"), p.get("status"), n_rel.get(p["id"], 0),
                m.get("grau"), m.get("forca"), m.get("intermediacao"), m.get("proximidade"), m.get("autovetor"),
                m.get("componente"), m.get("tamanho_componente"), m.get("comunidade"), m.get("isolado"),
            ]
            + [m.get("saltos", {}).get(o) for o in origens]
            + ["; ".join(i for i in inst if i), "; ".join(ds.aliases_de(p["id"])), "; ".join(p.get("fontes") or []), p.get("pendencia")]
        )
    _csv(path, cab, linhas)


def exportar_relacoes_csv(ds: Dataset, path: Path) -> None:
    from .weights import peso_relacao

    cab = [
        "id", "origem", "origem_nome", "destino", "destino_nome", "tipo", "subtipo", "simetrico", "periodo",
        "confianca", "status", "peso", "n_fontes", "fontes", "paginas", "descricao", "pendencia", "rompe", "autor_entrada", "data_entrada",
    ]
    linhas = []
    for r in ds.relacoes:
        fontes = [f for f in (r.get("fontes") or []) if isinstance(f, dict)]
        linhas.append(
            [
                r["id"], r["origem"], ds.nome(r["origem"]), r["destino"], ds.nome(r["destino"]), r["tipo"], r.get("subtipo"),
                r.get("simetrico", False), r.get("periodo"), r.get("confianca"), r.get("status"), peso_relacao(r),
                len({f.get("fonte") for f in fontes}), "; ".join(f.get("fonte", "") for f in fontes),
                "; ".join(str(f.get("pagina") or "") for f in fontes), r.get("descricao"), r.get("pendencia"),
                r.get("rompe"), r.get("autor_entrada"), r.get("data_entrada"),
            ]
        )
    _csv(path, cab, linhas)


# --------------------------------------------------------------------------- #
# GEXF / GraphML
# --------------------------------------------------------------------------- #

def _grafo_serializavel(G: nx.Graph, rel: dict[str, Any]) -> nx.Graph:
    H = nx.Graph()
    nos = rel["nos"]
    for n, d in G.nodes(data=True):
        m = nos.get(n, {})
        attrs = {
            "label": d.get("nome") or n,
            "atribuicao": d.get("atribuicao") or "",
            "papel": d.get("papel") or "outro",
            "status": d.get("status") or "",
            "grau": int(m.get("grau") or 0),
            "forca": float(m.get("forca") or 0.0),
            "intermediacao": float(m.get("intermediacao") or 0.0),
            "comunidade": int(m["comunidade"]) if m.get("comunidade") is not None else -1,
            "componente": int(m["componente"]) if m.get("componente") is not None else -1,
        }
        H.add_node(n, **attrs)
    for a, b, d in G.edges(data=True):
        H.add_edge(
            a,
            b,
            weight=float(d["peso"]),
            tipos="; ".join(d["tipos"]),
            tipo_dominante=d["tipo_dominante"],
            confiancas="; ".join(d["confiancas"]),
            n_relacoes=int(d["n_relacoes"]),
            n_fontes=int(d["n_fontes"]),
            relacoes="; ".join(d["relacoes"]),
        )
    return H


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #

def _tabela(cab: list[str], linhas: list[list[Any]]) -> str:
    out = ["| " + " | ".join(cab) + " |", "|" + "---|" * len(cab)]
    for ln in linhas:
        out.append("| " + " | ".join("—" if v is None else str(v) for v in ln) + " |")
    return "\n".join(out)


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def gerar_metricas_md(ds: Dataset, rel: dict[str, Any]) -> str:
    g = rel["global"]
    meta = rel["meta"]
    L: list[str] = []
    L.append("# GAP — Relatório de métricas da rede\n")
    L.append(f"Gerado em {meta['gerado_em']} · commit `{meta['commit'] or 'sem git'}` · fórmula de peso v{meta['versao_formula']}\n")
    L.append("> Nenhuma métrica decide sozinha. Este relatório indica sob quais critérios o conjunto se qualifica como escola e sob quais não (GAP_BRIEF §1.3).\n")

    L.append("## 1. Resumo\n")
    L.append(_tabela(["Indicador", "Valor"], [
        ["Pessoas na base", g["n_pessoas"]],
        ["Relações (linhas)", g["n_relacoes"]],
        ["Arestas (pares únicos)", g["n_arestas"]],
        ["Pessoas com ≥ 1 vínculo", g["n_conectados"]],
        ["Isoladas", g["n_isolados"]],
        ["Componentes (não triviais)", g["n_componentes"]],
        ["Maior componente", f"{g['maior_componente']} ({_pct(g['proporcao_no_maior_componente'])} da base)"],
        ["Densidade (conectados)", g["densidade_conectados"]],
        ["Coef. de agrupamento médio", g["agrupamento_medio"]],
        ["Transitividade", g["transitividade"]],
        ["Caminho médio (maior comp.)", g["caminho_medio_maior_componente"]],
        ["Diâmetro (maior comp.)", g["diametro_maior_componente"]],
        ["Modularidade (Louvain)", g["modularidade"]],
        ["Comunidades", g["n_comunidades"]],
        ["Fontes processadas / total", f"{meta['n_fontes_processadas']} / {meta['n_fontes']}"],
    ]))
    L.append("")

    L.append("## 2. Componentes\n")
    L.append("Componentes separados e pontes ausentes são leitura de dissidência estruturante (Bourdieu) ou de lacuna documental — a plataforma mostra, não esconde.\n")
    L.append(_tabela(["#", "Tamanho", "Papéis", "Membros"], [
        [c["id"], c["tamanho"], ", ".join(f"{k}: {v}" for k, v in c["papeis"].items()), ", ".join(ds.nome(m) for m in c["membros"])]
        for c in g["componentes"]
    ]))
    if rel["cobertura"]["isolados"]:
        L.append("\nIsolados: " + ", ".join(i["nome"] for i in rel["cobertura"]["isolados"]) + ".")
    L.append("")

    L.append("## 3. Comunidades (Zein 3, 4 — identidade de grupo)\n")
    L.append(f"Modularidade {g['modularidade']} · seed {meta['seed_comunidades']}. Alta modularidade = agrupamento real; baixa = rede difusa.\n")
    L.append(_tabela(["#", "Tamanho", "Papéis", "Atribuições", "Membros"], [
        [c["id"], c["tamanho"], ", ".join(f"{k}: {v}" for k, v in c["papeis"].items()),
         ", ".join(f"{k}: {v}" for k, v in c["atribuicoes"].items()), ", ".join(ds.nome(m) for m in c["membros"])]
        for c in g["comunidades"]
    ]))
    L.append("")

    L.append("## 4. Centralidades (Fleck — círculo esotérico vs. exotérico)\n")
    for chave, rot in (("grau", "Grau"), ("forca", "Força (grau ponderado)"), ("intermediacao", "Intermediação"),
                       ("proximidade", "Proximidade"), ("autovetor", "Autovetor")):
        itens = rel["ranking"][chave]
        L.append(f"**{rot}** — " + ("; ".join(f"{i['nome']} ({i[chave]})" for i in itens) if itens else "—") + "\n")

    L.append("## 5. Por tipo de relação\n")
    L.append("Topologias semelhantes entre tipos sustentam uma escola unificada; topologias diferentes argumentam contra uma origem única.\n")
    L.append(_tabela(["Tipo", "Relações", "Nós", "Arestas", "Comp.", "Maior comp.", "Densidade", "Agrupamento", "Caminho médio", "Mais conectado"], [
        [t["rotulo"], t["n_relacoes"], t["n_nos"], t["n_arestas"], t["n_componentes"], t["maior_componente"], t["densidade"],
         t["agrupamento_medio"], t["caminho_medio_maior_componente"], (t["top_grau"][0]["nome"] + f" ({t['top_grau'][0]['grau']})") if t["top_grau"] else None]
        for t in rel["por_tipo"].values()
    ]))
    L.append("")

    a = rel["auditoria_confianca"]
    L.append("## 6. Auditoria de confiança (Kris & Kurz — tópos narrativo)\n")
    L.append(_tabela(["Tipo", "Documentado", "Tradição oral", "Hipótese", "Total", "% documentado"], [
        [ROTULOS_TIPO[t], v["documentado"], v["tradicao_oral"], v["hipotese"], v["total"], _pct(v["proporcao_documentado"])]
        for t, v in a["por_tipo"].items()
    ] + [["**Total**", a["total"]["documentado"], a["total"]["tradicao_oral"], a["total"]["hipotese"], a["total"]["total"], _pct(a["total"]["proporcao_documentado"])]]))
    L.append(f"\nEnsino documentado: {_pct(a['proporcao_documentado_ensino'])} · Prática documentada: {_pct(a['proporcao_documentado_pratica'])}.\n")
    L.append(f"> {a['leitura']}\n")

    c = rel["convergencia_origens"]
    L.append("## 7. Convergência de origens (Zein 2)\n")
    if c["alcance"]:
        L.append(_tabela(["Origem", "Grau", "1 salto", "2 saltos", "3 saltos", "Alcançáveis", "% da rede conectada"], [
            [v["nome"], v["grau"], v["saltos_1"], v["saltos_2"], v["saltos_3"], v["alcancaveis"], _pct(v["proporcao_alcancavel"])]
            for v in c["alcance"].values()
        ]))
        L.append("")
    L.append(f"> {c['leitura']}\n")

    p = rel["proselitismo"]
    L.append("## 8. Proselitismo (Zein 5 — transmissão deliberada)\n")
    if p["emissores"]:
        L.append(_tabela(["Emissor", "Arestas de ensino emitidas"], [[e["nome"], e["saida"]] for e in p["emissores"]]))
        L.append("")
    L.append(f"> {p['leitura']}\n")

    t = rel["temporal"]
    L.append("## 9. Camada temporal\n")
    cov = t["cobertura"]
    L.append(f"Relações com período: {cov['n_com_periodo']} de {cov['n_relacoes']} ({_pct(cov['proporcao_com_periodo'])}). "
             f"Pessoas com alguma data: {cov['n_pessoas_com_datas']} de {cov['n_pessoas']}.\n")
    if t["decadas"]:
        L.append("Fatia = relações ativas na década; acumulado = relações iniciadas até o fim da década (rede 'nascendo'). Períodos abertos valem apenas pelo ano de início.\n")
        L.append(_tabela(["Década", "Rel. ativas", "Nós", "Arestas", "Comp.", "Rel. acumuladas", "Nós acum.", "Arestas acum.", "Comp. acum.", "Maior comp. acum."], [
            [d["rotulo"], d["fatia"]["n_relacoes"], d["fatia"]["n_nos"], d["fatia"]["n_arestas"], d["fatia"]["n_componentes"],
             d["acumulado"]["n_relacoes"], d["acumulado"]["n_nos"], d["acumulado"]["n_arestas"], d["acumulado"]["n_componentes"], d["acumulado"]["maior_componente"]]
            for d in t["decadas"]
        ]))
        L.append("")

    dep = rel["depoimentos"]
    L.append("## 10. Depoimentos sobre a Escola do Recife\n")
    L.append(f"{dep['n']} posições registradas: {dep['afirmam']} afirmam, {dep['negam']} negam, {dep['indefinidos']} indefinidas.\n")

    cob = rel["cobertura"]
    L.append("## 11. Cobertura\n")
    L.append(f"Pendências abertas: {cob['n_pendencias']} (ver `pendencias.md`). Fontes não processadas: {len(cob['fontes']['nao_processadas'])}. "
             f"Status das relações: {cob['status_relacoes']}. Status das pessoas: {cob['status_pessoas']}.\n")

    L.append("## 12. Método\n")
    L.append(f"- Peso: {meta['formula']}\n- Distância para caminhos ponderados = 1 / peso.\n- Comunidades: Louvain (NetworkX) com peso, seed {meta['seed_comunidades']}.\n"
             "- Intermediação e proximidade ponderadas pela distância; autovetor calculado no maior componente.\n"
             "- Relações e arestas são níveis distintos: contagens de tipo usam relações; métricas de rede usam arestas.\n")
    return "\n".join(L) + "\n"


def gerar_pendencias_md(ds: Dataset, rel: dict[str, Any]) -> str:
    cob = rel["cobertura"]
    L = ["# GAP — Pendências e pistas de pesquisa\n",
         f"Gerado em {rel['meta']['gerado_em']}. Esta lista é a agenda do próximo trabalho de campo (GAP_BRIEF §6.3).\n"]
    L.append("## Pendências registradas\n")
    if cob["pendencias"]:
        L.append(_tabela(["Entidade", "Id", "Quem / o quê", "Pendência"], [[p["entidade"], p["id"], p["nome"], p["pendencia"]] for p in cob["pendencias"]]))
    else:
        L.append("Nenhuma.")
    L.append("\n## Pessoas sem nenhum vínculo documentado\n")
    L.append(", ".join(f"{i['nome']}" + (f" ({i['papel']})" if i.get("papel") else "") for i in cob["isolados"]) or "Nenhuma.")
    L.append("\n\n## Pessoas citadas sem relação identificável (saída da extração)\n")
    if cob["mencoes_sem_relacao"]:
        L.append(_tabela(["Nome citado", "Ocorrências", "Fontes"], [[m["nome"], m["n"], ", ".join(m["fontes"])] for m in cob["mencoes_sem_relacao"]]))
    else:
        L.append("Nenhuma extração processada ainda.")
    L.append("\n\n## Fontes ainda não processadas\n")
    fontes = ds.fontes_por_id
    linhas = []
    for fid in cob["fontes"]["nao_processadas"]:
        f = fontes.get(fid, {})
        linhas.append([fid, f.get("autor"), f.get("titulo"), f.get("ano"), f.get("densidade"), "sim" if f.get("arquivo_local") else "não"])
    L.append(_tabela(["Id", "Autor", "Título", "Ano", "Densidade", "PDF local"], linhas) if linhas else "Nenhuma.")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# Orquestração
# --------------------------------------------------------------------------- #

def exportar_tudo(ds: Dataset, paths: Paths, rel: dict[str, Any] | None = None) -> dict[str, Path]:
    rel = rel or _relatorio(ds, paths)
    G = construir_grafo(ds)
    paths.export.mkdir(parents=True, exist_ok=True)
    saidas: dict[str, Path] = {}

    grafo = montar_grafo_json(ds, G, rel)
    saidas["grafo.json"] = paths.export / "grafo.json"
    write_json(saidas["grafo.json"], grafo, indent=None)

    saidas["metricas.json"] = paths.export / "metricas.json"
    write_json(saidas["metricas.json"], rel)

    saidas["metricas.md"] = paths.export / "metricas.md"
    saidas["metricas.md"].write_text(gerar_metricas_md(ds, rel), encoding="utf-8", newline="\n")

    saidas["pendencias.md"] = paths.export / "pendencias.md"
    saidas["pendencias.md"].write_text(gerar_pendencias_md(ds, rel), encoding="utf-8", newline="\n")

    saidas["pessoas.csv"] = paths.export / "pessoas.csv"
    exportar_pessoas_csv(ds, rel, saidas["pessoas.csv"])

    saidas["relacoes.csv"] = paths.export / "relacoes.csv"
    exportar_relacoes_csv(ds, saidas["relacoes.csv"])

    H = _grafo_serializavel(G, rel)
    saidas["grafo.gexf"] = paths.export / "grafo.gexf"
    nx.write_gexf(H, saidas["grafo.gexf"])
    saidas["grafo.graphml"] = paths.export / "grafo.graphml"
    nx.write_graphml(H, saidas["grafo.graphml"])

    paths.site_data.mkdir(parents=True, exist_ok=True)
    for nome in ("grafo.json", "metricas.json"):
        shutil.copyfile(saidas[nome], paths.site_data / nome)
    return saidas
