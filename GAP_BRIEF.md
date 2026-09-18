# GAP — Genealogia da Arquitetura Pernambucana
## Project brief for Claude Code

**Owner:** Paz (RPB:2 — research initiative of RPBA, Recife)
**Status:** design consolidated, prototypes exist, repository not yet created
**Date:** 2026-09-17

This document is the single source of truth for building the platform. It captures every decision made in the design discussion, the schema, the pipeline, the prototypes already produced, the corpus, and the phased build plan. Read it fully before writing code.

---

## 0. One-paragraph summary

GAP is a research instrument that maps the network of people who made Pernambuco's architecture over the last century — architects, urbanists, professors, and engineers with architectural attribution — as a graph of documented relationships (kinship, master–apprentice, employment, study, partnership, dissidence, co-authorship). Its scientific purpose is to test, with quantitative evidence, whether the so-called **"Escola do Recife"** existed as a school in the sense the historiography uses for "Escola Paulista" and "Escola Carioca". Its operational purpose is to be an organism: a database that grows easily as new sources are processed, with every edge carrying provenance and confidence, and a web front end that lets anyone explore the network like Connected Papers. Think of it as a Senseable-City-Lab-style side project: rigorous data behind an attractive public face, publishable in recognized venues.

---

## 1. Research question and conceptual frame

### 1.1 The question
Did a "Escola do Recife" exist? Historiography disputes it. Some place its origin with **Luiz Nunes** and his team at the DAC/PE (1934–1937); others with the first professors of the EBAP architecture course after 1949 — **Mário Russo, Delfim Amorim, Acácio Gil Borsoi, Heitor Maia Neto** — and their disciples. Some practitioners deny it outright (Maurício Castro: no communication of ideas, no professional union). The project does not assume an answer.

### 1.2 What "school" means — operational criteria
From Ruth Verde Zein (*A arquitetura da escola paulista brutalista*, PROPAR/UFRGS, 2005), the most explicit definition available in Portuguese. A school requires:

1. Qualifiable "spiritual kinship" ties among members
2. Shared beliefs, influences or common origins in the work
3. Group identity — restricted enough to not include everyone
4. Cohesion, possibly informal, manifested through shared interests
5. Some proselytizing intent, even if not operative

Additional frames used: Randall Collins (*The Sociology of Philosophies*, 1998 — networks of master–pupil ties as the locus of intellectual creativity; **closest methodological precedent**), Diana Crane (invisible colleges), Ludwik Fleck (thought collectives, esoteric vs. exoteric circles), Bourdieu (field, consecration, dissidence as structuring), Howard Becker (art worlds as cooperation networks), Kris & Kurz (the master–disciple narrative as a biographical *topos* — a hygiene warning).

### 1.3 Criteria → graph metrics (the core analytical contract)

| Theoretical criterion | Graph metric | Reading |
|---|---|---|
| Restricted group identity (Zein 3, 4) | Community detection / modularity; internal vs. external density | High modularity = real grouping; low = diffuse network |
| Common origins (Zein 2) | Path convergence toward few origin nodes | Do most paths pass through Russo/Borsoi/Amorim? |
| Proselytism (Zein 5) | Share and direction of `estudo` + `mestre-aprendiz` edges | Many teaching edges from few nodes = deliberate transmission |
| Informal cohesion (Zein 4) | Clustering coefficient; average path length | High cohesion with few formal ties = invisible college |
| Communication + professional union (Castro's objection) | Institutional co-participation edges (IAB/PE boards, faculty, congresses) | Empirical test of the strictest objection in the debate |
| Esoteric vs. exoteric circle (Fleck) | Betweenness and degree centrality | Core vs. periphery without value judgement |
| Structuring dissidence (Bourdieu) | Separate components; missing bridge nodes | Visible ruptures = contested field, not homogeneous school |
| Narrative *topos* (Kris & Kurz) | Confidence distribution per edge type | If `mestre-aprendiz` edges are systematically less documented than `societario`, suspect narrative convention |

No single metric decides. The publishable output is a statement of *under which criteria* the set qualifies as a school and under which it does not.

**Known limitation to state explicitly:** the graph is about people; the historiographic claim is about a design tradition. Dense people-networks do not imply formal coherence in the works, nor vice versa.

---

## 2. Decisions already made

| Topic | Decision |
|---|---|
| Time span | As early as data allows; Luiz Nunes (1934) is the earliest recognizable nodal figure |
| Geography | Anyone with cohesive connections to the Pernambuco network, including people who left and returned or came from outside and stayed |
| Who counts as a node | Architects, urbanists, architecture-school professors; engineers when they have architectural attribution (early-century role distinctions differ from today's). What matters is the attribution, not the title held at the time |
| Nodes | **People only.** Works and institutions are metadata, not nodes. Clusters by metadata must be queryable (e.g. "who taught at UFPE", "who worked at Jerônimo & Pontual") |
| Authorship | Paz is the sole editor. Others may submit via a form; submissions enter the same triage queue and require Paz's approval |
| Contribution model | **Pull request.** Git is the source of truth |
| Institutional home | Personal project, to be offered to LIAU/UFPE (Guilah Naslavsky); may integrate other instances |
| Relation taxonomy | 7 fixed types (below). "Influence without contact" was **rejected** — too speculative |
| Extending the taxonomy | Only when an uncategorized relation recurs. Mechanism: free-text `subtipo` field; promote to a type when it appears 3+ times |
| Confidence | Three levels: `documentado`, `tradicao_oral`, `hipotese` |
| Sources | Every edge requires a source. Edges without source are allowed only as `hipotese` with an open `pendencia` field, clearly marked |
| Source format | Links as text (bibliographic reference + URL/page) |
| Primary output | **Quantitative analysis.** Exploratory visualization is important for communicating but secondary |
| Temporal layer | Not priority for v1, but every relation carries `periodo` when known; time is a metric wherever available |
| Audience | Data input: Paz and academic peers. Output: students and lay public — the front end must be attractive |
| Hosting | Static site generated from the repository; no live database server |
| Language of data | Portuguese (field names, relation types, descriptions). Code and comments may be English |

---

## 3. Data model

Source of truth: structured files in a Git repository. Single growing file per entity type (JSON Lines), diff-friendly, trivially loadable in Python.

```
data/
  pessoas.jsonl        # one person per line
  relacoes.jsonl       # one relation per line
  depoimentos.jsonl    # recorded positions on the "Escola do Recife" question
  fontes.jsonl         # bibliographic sources, one per line, referenced by id
  vocabularios/
    instituicoes.yaml  # controlled vocabulary for institutions/offices
    aliases.yaml       # name variants → canonical person id
```

### 3.1 pessoa
```json
{
  "id": "luiz-nunes",
  "nome": "Luiz Nunes",
  "nome_completo": "Luiz de Barros Freire Nunes",
  "nascimento": 1907,
  "morte": 1937,
  "local_nascimento": "Recife, PE",
  "titulo_epoca": "engenheiro-arquiteto",
  "atribuicao": "arquiteto",
  "papel_historiografico": "precursor",
  "formacao": [{"instituicao": "ENBA", "curso": "Arquitetura", "ano_conclusao": 1930}],
  "atuacao": [{"tipo": "orgao_publico", "nome": "DAC/PE", "periodo": "1934-1937"}],
  "notas": "free text",
  "status": "verificado",
  "fontes": ["naslavsky-1998"],
  "data_entrada": "2026-09-17"
}
```
- `id`: slug, unique, stable. Never rename; use `aliases.yaml` for variants.
- `atribuicao`: `arquiteto | urbanista | engenheiro | professor | outro` — the classification that matters for the network.
- `papel_historiografico`: `precursor | mestre | discipulo | null` — lets the UI highlight consensus figures even when they have no documented edge yet (Luiz Nunes problem, see §7.3).
- `status`: `rascunho | verificado | contestado`. Marks *Paz's review*, distinct from evidence quality.
- `atuacao[].nome` and `formacao[].instituicao` must match `vocabularios/instituicoes.yaml` — this is what makes metadata clustering reliable.

### 3.2 relacao
```json
{
  "id": "rel-0001",
  "origem": "mario-russo",
  "destino": "reginaldo-esteves",
  "tipo": "mestre-aprendiz",
  "subtipo": null,
  "simetrico": false,
  "periodo": "1950-1954",
  "descricao": "integrou equipe do ETCUR coordenada por Russo",
  "confianca": "documentado",
  "fontes": [{"fonte": "afonso-2008", "pagina": "6", "trecho": "short quoted sentence"}],
  "pendencia": null,
  "rompe": null,
  "status": "rascunho",
  "data_entrada": "2026-09-17",
  "autor_entrada": "paz"
}
```
- `tipo` enum: `heranca | mestre-aprendiz | estudo | trabalho | societario | dissidencia | coautoria-pontual`
- Directionality: `heranca`, `mestre-aprendiz`, `estudo`, `dissidencia` are asymmetric (origem → destino). `trabalho`, `societario`, `coautoria-pontual` may be symmetric (`simetrico: true`).
- `dissidencia` may reference the relation it breaks via `rompe: "rel-XXXX"`.
- **Multiple relations between the same pair are expected and valuable.** Do not deduplicate across types. Do deduplicate the same (pair, tipo) across sources: instead of a new line, append the new source to `fontes[]`.
- `fontes[].trecho`: the literal sentence that grounds the relation — makes human review fast.
- **`peso` is never stored.** It is computed at analysis time (§6.2).

### 3.3 depoimento
Positions people took on the existence of the school. Not a relation; a separate entity.
```json
{
  "id": "dep-0001",
  "pessoa": "mauricio-castro",
  "existe_escola": false,
  "argumento": "faltou comunicação de ideias e união profissional no meio local",
  "fonte": {"fonte": "afonso-2008", "pagina": "7"},
  "data_depoimento": "2005-02"
}
```

### 3.4 fonte
```json
{"id": "afonso-2008", "tipo": "artigo", "autor": "AFONSO, Alcília", "titulo": "A produção arquitetônica moderna dos primeiros discípulos de uma Escola", "veiculo": "Arquitextos 098.05, Vitruvius", "ano": 2008, "url": "https://vitruvius.com.br/revistas/read/arquitextos/09.098/128", "arquivo_local": "raw_pdfs/afonso-2008.pdf", "processado": true}
```

### 3.5 Validation rules (run in CI on every PR)
1. Referential integrity: every `origem`/`destino`/`pessoa` exists in `pessoas.jsonl`; every `fontes[].fonte` exists in `fontes.jsonl`.
2. Enum validity for `tipo`, `confianca`, `status`, `atribuicao`.
3. Institution names in `atuacao`/`formacao` must exist in `instituicoes.yaml`.
4. **Name quality:** flag any `nome` with a single token (e.g. "Didier") — referential checks do not catch bad identifiers.
5. `confianca: documentado` requires at least one entry in `fontes[]`.
6. `hipotese` with empty `fontes[]` requires non-empty `pendencia`.
7. Duplicate (origem, destino, tipo) lines are rejected — merge sources instead.

---

## 4. Architecture

Three layers, deliberately decoupled:

```
┌──────────────────────────────────────────────────────────────┐
│ LAYER 1 — SOURCE OF TRUTH                                     │
│ Git repository with data/*.jsonl. Every change is a commit.  │
│ Pull requests = review + history + auditability + citability │
│ (a commit hash is the "state of the data" for a paper).       │
└──────────────────────────────────────────────────────────────┘
        ▲ commits from triage              │ read on build
┌───────┴──────────────────────┐   ┌───────▼──────────────────────┐
│ LAYER 0 — INGESTION FUNNEL   │   │ LAYER 2 — ANALYSIS           │
│ PDF → chunks → lexical       │   │ Python + NetworkX.           │
│ prefilter → LLM extraction → │   │ Computes weights, metrics,   │
│ entity resolution → dedup →  │   │ communities, ego-networks,   │
│ human triage UI → commit     │   │ temporal slices. Exports.    │
└──────────────────────────────┘   └───────┬──────────────────────┘
                                           │ export JSON
                                   ┌───────▼──────────────────────┐
                                   │ LAYER 3 — PRESENTATION       │
                                   │ Static site (D3). Graph,     │
                                   │ ego-network focus, filters,  │
                                   │ metrics, person pages.       │
                                   └──────────────────────────────┘
```

Why no database server: single editor, PR model is native to Git, zero infra cost, zero attack surface, backup for free, and citable commits. Complex live queries are pre-computed at build time; interactive exploration (zoom, filter, focus) runs in the browser.

### 4.1 Recommended stack
- **Python 3.11+**: `networkx`, `pymupdf` (PDF text with page numbers), `rapidfuzz` (entity resolution), `pyyaml`, `anthropic` (extraction), `fastapi` + `uvicorn` (local internal app), `GitPython` (commits from the triage UI).
- **Front end**: vanilla HTML/JS + **D3 v7** from cdnjs. No framework needed for v1. Fonts: Archivo + Space Mono (Google Fonts), already used in the prototypes.
- **Extraction model**: Claude Haiku (cheap; volume after prefilter is small). Escalate to Sonnet only for chunks the triage marks as ambiguous.
- **Hosting of the public site**: GitHub Pages / Netlify / own domain — static.
- **Environment**: Paz works on **Windows**. Paths use backslashes; corpus at `C:\Users\Letícia\Desktop\RPB2\GAP\raw_pdfs`. Use `pathlib` everywhere.

---

## 5. Ingestion funnel (Layer 0) — the hard part

The real problem is **signal density**: a 200-page thesis typically yields 2–3 relations. Sending whole documents to an LLM is expensive and, worse, inflates hallucinated relations (co-mention ≠ relation). Hence a funnel.

### Stage 0 — Text with position
PDF → text preserving **page number and paragraph index**. Provenance is a schema requirement. Store as `work/<fonte-id>/chunks.jsonl` with `{chunk_id, pagina, paragrafo, texto}`. Chunk by paragraph, not by fixed token count — relations live in single sentences.

### Stage 1 — Lexical prefilter (no LLM, seconds, free)
A chunk passes only if it contains **both**:
- at least one person name — from the gazetteer (`pessoas.jsonl` + `aliases.yaml`, growing) plus capitalized-bigram detection for unknown names;
- at least one relational cue from a Portuguese lexicon: *trabalhou com / trabalhou para / estagiou / foi aluno de / sob orientação de / sócio / associou-se / escritório de / equipe de / colaborou / convidado por / filho de / filha de / irmão de / irmã de / casado com / casada com / esposa / marido / primo / discípulo / formou-se com / projetaram juntos / em parceria com / rompeu / deixou o escritório / fundou com / diretoria*.

Tune for **recall**: false positives are cheap (discarded in triage), missed relations are expensive. Log the discard rate per document so Paz can audit aggressiveness. Expect 90–95% of paragraphs cut.

### Stage 2 — Structured extraction (LLM, candidates only)
Send each candidate chunk **with its neighbouring paragraphs** (anaphora: "ele então trabalhou com…" needs the previous paragraph). Prompt must be explicitly conservative:
- return `[]` when no clear relation is stated;
- co-mention of two names is **not** a relation;
- output strict JSON matching the `relacao` schema plus `trecho` (literal grounding sentence) and `pagina`;
- also output `mencoes_sem_relacao`: names mentioned with no identifiable relation (feeds the "people cited but unlinked" list — research leads).

Everything from this stage enters as `status: rascunho`. `confianca` is set from the source type (interview/deposition → `documentado`; author's inference → `hipotese`), then reviewed.

### Stage 3 — Entity resolution (most underestimated problem)
"Maurício do Passo Castro", "Maurício Castro", "Castro", "o arquiteto Castro" are one node. Fuzzy-match extracted names against canonical names + aliases (`rapidfuzz`). Three outcomes:
- score above threshold → assign existing id automatically, show the match in triage;
- ambiguous or new → **human queue**, never auto-decided;
- single-token names → always human queue, provisional id + `pendencia`.
When Paz confirms a variant, append it to `aliases.yaml` — the system learns.

### Stage 4 — Deduplication and reinforcement
If (origem, destino, tipo) already exists, do not create a new line: append the new source to `fontes[]`. Recurrence across independent sources is qualitatively stronger evidence and raises the computed weight (§6.2).

### Stage 5 — Triage UI (what makes the flow sustainable)
Single-item review: source sentence highlighted with grey context before/after, proposed relation pre-filled, alerts (entity match, duplicate pair, weak evidence, out of scope, not-a-relation). Actions: **A** accept, **D** discard, **S** defer, **Z** undo, **1–7** set type. Accepted items are appended to `relacoes.jsonl` and committed (branch + PR, or direct commit to a `triage/<fonte-id>` branch). Paz never types JSON.

Must also support: **manual direct entry** (for relations a specialist reader infers that the machine cannot), **create new person from the queue**, **edit the grounding excerpt**, and routing a candidate to `depoimentos` instead of `relacoes`.

External contributions (form) enter the same queue with `autor_entrada` set to the submitter.

---

## 6. Analysis layer (Layer 2)

### 6.1 Two levels, kept separate
- **Relations** (lines in `relacoes.jsonl`): count these when the question is "how many co-authorship relations exist".
- **Edges** (unique person pairs): the graph collapses multiple relations into one edge with `tipos: [...]`. Metrics run on edges.
Scripts must never confuse the two.

### 6.2 Weight (computed, never stored)
```
peso(edge) = Σ over relations on the pair of  w(confianca) × (1 + 0.5 × (n_fontes_independentes − 1))
w = {documentado: 1.0, tradicao_oral: 0.6, hipotese: 0.3}
```
Weight drives layout distance (Connected-Papers behaviour) and the ranked neighbour list. Keep the formula in one function, documented, versioned.

### 6.3 Metrics to compute on every build
- Node: degree, weighted degree ("força"), betweenness, closeness, eigenvector; hop distances from selected origins (Luiz Nunes, Russo, Borsoi, Amorim).
- Graph: components, modularity + community assignment (Louvain), clustering coefficient, average path length, density.
- Per relation type: subgraph metrics (compare the topology of the kinship network vs. the study network vs. the partnership network — structurally similar topologies support a unified school; different ones argue against a single origin).
- Confidence audit: distribution of `confianca` per `tipo` (the Kris & Kurz test).
- Coverage: nodes with degree 0; people cited but unlinked; open `pendencia` list (this doubles as the next fieldwork agenda).
- **Temporal**: when `periodo` exists, slice the graph by decade and compute the above per slice; a "network birth" animation is a later feature, but the per-decade tables are v1.

### 6.4 Ego-network
`nx.ego_graph(G, id, radius=2)`, with neighbours ranked by `peso`. This is the primary exploration mode of the front end.

### 6.5 Exports (all regenerated on build)
- `export/grafo.json` — nodes + edges + computed metrics, consumed by the site.
- `export/pessoas.csv` — all names with ids, atribuicao, dates, degree, força, community.
- `export/relacoes.csv` — flat table of relations with sources.
- `export/metricas.json` and `export/metricas.md` — the full metric report, human-readable.
- `export/grafo.gexf` / `.graphml` — for Gephi and other tools.
- `export/pendencias.md` — open research leads.

---

## 7. Presentation layer (Layer 3)

### 7.1 Prototype already exists
`genealogia-prototipo.html` (single file, D3, data embedded) implements: force layout with weight-proportional distance; node size by força; colour by `papel_historiografico`; edge colour by dominant type, dashed for `hipotese`; click-to-focus ego mode with concentric hop rings and dimming; ranked neighbour panel with chained navigation; type filters; toggle for hypothetical edges; metrics panel; depoimento display. **Port it to load `export/grafo.json` instead of embedded data**; keep the visual language.

### 7.2 Required additions for v1
- Person page (route or panel): biography fields, atuação timeline, all relations with sources, depoimento if any.
- Search by name (with aliases).
- Metadata clustering: filter/highlight by institution (`atuacao.nome`) — e.g. "everyone who taught at UFPE".
- Metrics view: tables from `metricas.json`; per-type subgraph comparison.
- Provenance everywhere: hovering an edge shows the source(s) and excerpt.
- Isolated nodes rendered with dashed outline, never hidden (§7.3).

### 7.3 The Luiz Nunes problem (design principle)
In the first processed source, Luiz Nunes had no documented personal tie to the 1950s group and disappeared from the main component. This is *correct* (no evidence in that source) but misleading to a viewer who expects the consensus founder. Resolution: (a) `papel_historiografico` lets the UI mark him as precursor even when unlinked; (b) his team relations (DAC/PE: Joaquim Cardozo, Burle Marx, Fernando Saturnino de Brito, João Correia Lima, Antônio Bezerra Baltar) come from other sources and must be entered as `trabalho`/`coautoria-pontual`; (c) a simulation showed that adding his team creates a separate 1930s cluster **that still does not connect to the 1950s core** — the missing bridge between the two generations is itself a research finding. Candidate bridge: Ayrton (Airton) de Carvalho. The platform must make such gaps visible, not paper over them.

### 7.4 Design language
Tokens from the prototypes: ground `#E8E4DA`, panel `#F2EFE8`, ink `#14161A`, graphite `#6B6E73`, hairline `#C4BFB4`; blue `#22527A` (mestre / mestre-aprendiz), rust `#9C3B1B` (discípulo / societário), moss `#4A6B4F` (estudo), plum `#6B2D5C` (precursor / herança), teal `#2F6D6A` (coautoria), ochre `#7A6420` (trabalho), red `#B02020` (dissidência). Typography: Archivo (UI) + Space Mono (data). Archival-technical register; not a generic dashboard.

---

## 8. Corpus

- **Raw PDFs already separated by Paz:** `C:\Users\Letícia\Desktop\RPB2\GAP\raw_pdfs` — start there. First action: inventory this folder (`fontes.jsonl` skeleton with `processado: false`).
- **Bibliography of the field** (≈40 references, ranked by relation density): `bibliografia-gap.md`.
- **Conceptual bibliography** (what a "school" is): `conceito-escola-bibliografia.md`.
- **Open-access corpus with download links** (theses, Docomomo proceedings, Vitruvius articles, concurso databases): produced by the research pass; highest-density items to process first:
  1. Andréa Halász Gáti Porto, thesis on architect couples (UFPE 2021) — kinship/spouse/partnership ties, severely under-represented in canonical sources
  2. Erick Oliveira Silva, dissertation on Jerônimo & Pontual (UFPE 2020)
  3. Ronaldo L'Amour Filho, dissertation on Wandenkolk Tinoco (UFPE 2023)
  4. Alcília Afonso, *A produção arquitetônica moderna dos primeiros discípulos de uma Escola* (Arquitextos 098.05) — **already processed manually; use as the gold-standard test set** (§10)
  5. Rita de Cássia Vaz, *Luiz Nunes* (FAU-USP 1989) and Naslavsky 1998 — the DAC/PE team
  6. Docomomo Norte/Nordeste proceedings 1º–10º (index pages per edition; PDFs behind each article's page)
- Not open access, obtain otherwise: *Delfim Amorim: arquiteto* (IAB-PE 1981/1991); Moreira (org.), *Arquitetura Moderna no Norte e Nordeste do Brasil* (FASA 2007); Naslavsky 2004 thesis (check teses.usp.br).
- Primary sources for later fieldwork: CREA-PE archive; *Folha da Manhã* Sunday architecture page (IAB/PE, 1950s, Fundaj hemeroteca); IAB/PE board minutes; UFPE Faculty of Architecture records; LIAU/UFPE and LAHOI/UFPE oral-history collections.
- Concurso databases (team composition = co-authorship): Suzuki thesis (FAU-USP 2016, 480 concursos); `concursosdeprojeto.org`. A "Toscano" database mentioned by Paz was **not confirmed** — verify before relying on it.

**Corpus bias to manage:** most literature presupposes the school exists and organizes material as masters and disciples. Marques & Naslavsky, *Eu vi o modernismo nascer… foi no Recife* (Arquitextos 131.02), is the explicit counter-voice; process it early and record its positions as `depoimentos`.

---

## 9. Repository layout (to create)

```
gap/
  README.md
  GAP_BRIEF.md                 # this file
  data/
    pessoas.jsonl
    relacoes.jsonl
    depoimentos.jsonl
    fontes.jsonl
    vocabularios/instituicoes.yaml
    vocabularios/aliases.yaml
  raw_pdfs/                    # gitignored; local corpus
  work/                        # gitignored; chunks, candidates per source
  gap/                         # python package
    ingest/   (pdf_to_chunks.py, prefilter.py, lexicon.py, extract.py, resolve.py, dedup.py)
    validate/ (schema.py, ci_checks.py)
    analysis/ (graph.py, weights.py, metrics.py, temporal.py, export.py)
    app/      (server.py — FastAPI; templates/; static/)   # internal triage app
    cli.py                     # `gap ingest <pdf>`, `gap triage <fonte>`, `gap build`, `gap export`
  site/                        # generated static public site (D3)
  tests/
    gold/afonso-2008/          # gold-standard relations for the benchmark
  .github/workflows/validate.yml   # runs validation on every PR; builds site on merge
```

---

## 10. Build plan

### Phase 1 — Foundation (repo, schema, validation, seed)
- Create the repository and layout above.
- Implement JSONL schemas (pydantic) and the CI validation checks in §3.5.
- Load the seed data (Appendix A) and the Afonso 2008 source entry.
- Implement `gap build`: load → graph → weights → metrics → exports (§6).
- Port the visualization prototype to read `export/grafo.json`.
- **Deliverable:** `gap build` regenerates everything from a clean checkout; site renders the seed graph.

### Phase 2 — Ingestion funnel + triage app
- Stage 0–4 as specified; store intermediates under `work/`.
- Triage app (port `genealogia-triagem.html`, back it with FastAPI; accept → append + commit on a branch).
- Inventory `raw_pdfs` into `fontes.jsonl`.
- **Benchmark:** run the funnel on the Afonso 2008 PDF/HTML and compare to the gold set (Appendix A). Target ≥ 80% recall on documented relations with ≤ 20% false candidates surviving prefilter+extraction. Below target: improve lexicon and gazetteer before scaling.

### Phase 3 — Scale the corpus
- Process the four high-density theses, then Docomomo N/NE proceedings in bulk.
- Grow `aliases.yaml` and `instituicoes.yaml` as triage runs.
- Enter the DAC/PE team from Vaz 1989 / Naslavsky 1998; look for the 1930s→1950s bridge.

### Phase 4 — Analysis for publication
- Per-type subgraph comparison; community detection; origin-convergence tests; confidence audit; temporal slices by decade.
- `metricas.md` as a reproducible appendix; tag a commit as the data state for submission.

### Phase 5 — Public face
- Person pages, search, institution clusters, provenance on hover, metrics view. Publish the static site.
- External submission form → triage queue.

---

## 11. Non-negotiable standards

1. **Never invent a relation.** Co-mention is not a relation. When in doubt, `hipotese` + `pendencia`, or nothing.
2. **Every edge has provenance** (source id, page, excerpt) or is visibly marked as lacking it.
3. **Confidence ≠ review status.** `confianca` describes the evidence; `status` describes Paz's review. Keep both.
4. **Stated, not inferred, for people facts.** Dates, roles and kinship come from sources, not from the model's background knowledge.
5. **Weights are computed, never hand-set.** Anyone can recompute them from raw data.
6. **Ids are permanent.** Rename only through aliases.
7. **Data language is Portuguese.** UI language is Portuguese. Code may be English.
8. **Reproducibility:** `gap build` from a clean checkout must regenerate every export and the site.
9. **Gaps are shown, not hidden.** Isolated nodes, missing bridges and open pendências are outputs.
10. **Copyright:** store short grounding excerpts only; never reproduce long passages of sources in the public site.

---

## 12. Open decisions (surface to Paz when they block work)

- Whether foreign figures who explain formation (e.g. Max Bill, M. Patrix, J. Vienot for Reginaldo Esteves) become nodes with a flag, or remain notes on the person.
- Whether to add `equipe-institucional` as an 8th relation type (DAC/PE, ETCUR, IAB/PE boards) — it has already recurred; likely yes.
- Whether triage commits go to a branch per source (`triage/<fonte-id>`) with a PR, or directly to `main` given a single editor.
- Whether the internal app and the public site are one codebase with two modes, or two.
- Whether the project has its own visual identity/domain or lives under RPB:2.

---

## Appendix A — Seed data (from Afonso 2008, manually extracted)

Use as `data/*.jsonl` initial content and as `tests/gold/afonso-2008/`. Everything here is `status: rascunho` pending Paz's review except the five canonical figures marked `verificado`.

### A.1 pessoas.jsonl
```jsonl
{"id":"luiz-nunes","nome":"Luiz Nunes","papel_historiografico":"precursor","status":"verificado"}
{"id":"mario-russo","nome":"Mario Russo","papel_historiografico":"mestre","status":"verificado"}
{"id":"acacio-gil-borsoi","nome":"Acácio Gil Borsoi","papel_historiografico":"mestre","status":"verificado"}
{"id":"delfim-amorim","nome":"Delfim Amorim","papel_historiografico":"mestre","status":"verificado"}
{"id":"heitor-maia-neto","nome":"Heitor Maia Neto","papel_historiografico":"mestre","status":"verificado"}
{"id":"mauricio-castro","nome":"Mauricio do Passo Castro","papel_historiografico":"discipulo","status":"rascunho"}
{"id":"everaldo-gadelha","nome":"Everaldo Gadelha","papel_historiografico":"discipulo","status":"rascunho"}
{"id":"reginaldo-esteves","nome":"Reginaldo Luiz Esteves","papel_historiografico":"discipulo","status":"rascunho"}
{"id":"marcos-domingues","nome":"Marcos Domingues","papel_historiografico":"discipulo","status":"rascunho"}
{"id":"carlos-correia-lima","nome":"Carlos Correia Lima","papel_historiografico":"discipulo","status":"rascunho"}
{"id":"edison-lima","nome":"Edison Rodrigues de Lima","papel_historiografico":"discipulo","status":"rascunho"}
{"id":"waldeci-pinto","nome":"Waldeci Fernandes Pinto","papel_historiografico":"discipulo","status":"rascunho"}
{"id":"paulo-vaz","nome":"Paulo Vaz","papel_historiografico":"discipulo","status":"rascunho"}
{"id":"augusto-reynaldo","nome":"Augusto Reynaldo","nascimento":1924,"morte":1958,"papel_historiografico":"discipulo","status":"rascunho"}
{"id":"dilson-mota","nome":"Dílson Mota","papel_historiografico":"discipulo","status":"rascunho"}
{"id":"helio-moreira","nome":"Hélio Moreira","papel_historiografico":"discipulo","status":"rascunho"}
{"id":"ana-regina-moreira","nome":"Ana Regina Moreira","papel_historiografico":"discipulo","status":"rascunho"}
{"id":"helio-coelho-correia","nome":"Hélio Coelho Correia","atribuicao":"outro","status":"rascunho"}
{"id":"arlindo-pontual","nome":"Arlindo Pontual","atribuicao":"engenheiro","status":"rascunho"}
{"id":"airton-carvalho","nome":"Airton Carvalho","atribuicao":"engenheiro","status":"rascunho"}
{"id":"emerson-pinheiro","nome":"Emerson Pinheiro","atribuicao":"engenheiro","status":"rascunho"}
{"id":"eduardo-burle-ferreira","nome":"Eduardo Burle Ferreira","status":"rascunho"}
{"id":"vital-pessoa-melo","nome":"Vital Pessoa de Melo","status":"rascunho"}
{"id":"didier-dnocs","nome":"Didier","status":"rascunho","pendencia":"confirmar sobrenome em outra fonte"}
{"id":"renato-torres","nome":"Renato Torres","status":"rascunho"}
{"id":"helio-maia","nome":"Hélio Maia","status":"rascunho"}
```

### A.2 relacoes.jsonl (source for all: `afonso-2008`)
```jsonl
{"origem":"mario-russo","destino":"mauricio-castro","tipo":"estudo","confianca":"documentado","status":"rascunho"}
{"origem":"mario-russo","destino":"reginaldo-esteves","tipo":"estudo","confianca":"documentado","periodo":"1950-1954","status":"rascunho"}
{"origem":"acacio-gil-borsoi","destino":"reginaldo-esteves","tipo":"estudo","confianca":"documentado","status":"rascunho"}
{"origem":"mario-russo","destino":"marcos-domingues","tipo":"estudo","confianca":"documentado","periodo":"1950-1954","status":"rascunho"}
{"origem":"acacio-gil-borsoi","destino":"marcos-domingues","tipo":"estudo","confianca":"documentado","status":"rascunho"}
{"origem":"mario-russo","destino":"carlos-correia-lima","tipo":"estudo","confianca":"documentado","periodo":"1949-1954","status":"rascunho"}
{"origem":"acacio-gil-borsoi","destino":"carlos-correia-lima","tipo":"estudo","confianca":"documentado","status":"rascunho"}
{"origem":"delfim-amorim","destino":"carlos-correia-lima","tipo":"estudo","confianca":"documentado","descricao":"professor com quem mais se identificava","status":"rascunho"}
{"origem":"mario-russo","destino":"waldeci-pinto","tipo":"estudo","confianca":"documentado","periodo":"1949-1954","status":"rascunho"}
{"origem":"acacio-gil-borsoi","destino":"waldeci-pinto","tipo":"estudo","confianca":"documentado","status":"rascunho"}
{"origem":"delfim-amorim","destino":"waldeci-pinto","tipo":"estudo","confianca":"documentado","status":"rascunho"}
{"origem":"acacio-gil-borsoi","destino":"augusto-reynaldo","tipo":"estudo","confianca":"documentado","descricao":"Borsoi elogiou a criatividade do aluno em depoimento","status":"rascunho"}
{"origem":"mario-russo","destino":"mauricio-castro","tipo":"mestre-aprendiz","confianca":"documentado","descricao":"convidado por Russo, ainda estudante, para o ETCUR","status":"rascunho"}
{"origem":"mario-russo","destino":"reginaldo-esteves","tipo":"mestre-aprendiz","confianca":"documentado","descricao":"integrou equipe do ETCUR coordenada por Russo","status":"rascunho"}
{"origem":"mario-russo","destino":"waldeci-pinto","tipo":"mestre-aprendiz","confianca":"documentado","descricao":"trabalhou no ETCUR com Russo a partir de 1954","periodo":"1954-","status":"rascunho"}
{"origem":"arlindo-pontual","destino":"reginaldo-esteves","tipo":"mestre-aprendiz","confianca":"documentado","descricao":"orientação profissional em obras de infraestrutura na empresa Júlio Maranhão","status":"rascunho"}
{"origem":"helio-coelho-correia","destino":"reginaldo-esteves","tipo":"mestre-aprendiz","confianca":"documentado","descricao":"primeiro trabalho de Esteves, projetos ecléticos","status":"rascunho"}
{"origem":"mauricio-castro","destino":"heitor-maia-neto","tipo":"heranca","subtipo":"primos","simetrico":true,"confianca":"documentado","status":"rascunho"}
{"origem":"mauricio-castro","destino":"helio-maia","tipo":"heranca","subtipo":"primos","simetrico":true,"confianca":"documentado","status":"rascunho"}
{"origem":"mauricio-castro","destino":"reginaldo-esteves","tipo":"societario","simetrico":true,"confianca":"documentado","descricao":"Castro & Esteves, a partir de 1964","periodo":"1964-","status":"rascunho"}
{"origem":"mauricio-castro","destino":"heitor-maia-neto","tipo":"societario","simetrico":true,"confianca":"documentado","descricao":"escritório anterior à sociedade com Esteves","status":"rascunho"}
{"origem":"mauricio-castro","destino":"helio-maia","tipo":"societario","simetrico":true,"confianca":"documentado","status":"rascunho"}
{"origem":"reginaldo-esteves","destino":"vital-pessoa-melo","tipo":"societario","simetrico":true,"confianca":"documentado","descricao":"edifício CELPE","status":"rascunho"}
{"origem":"marcos-domingues","destino":"carlos-correia-lima","tipo":"societario","simetrico":true,"confianca":"documentado","descricao":"sociedade de longa data em escritório próprio","status":"rascunho"}
{"origem":"waldeci-pinto","destino":"emerson-pinheiro","tipo":"societario","simetrico":true,"confianca":"documentado","status":"rascunho"}
{"origem":"waldeci-pinto","destino":"didier-dnocs","tipo":"societario","simetrico":true,"confianca":"documentado","descricao":"concurso e obra do DNOCS, 1958","periodo":"1958","status":"rascunho"}
{"origem":"waldeci-pinto","destino":"renato-torres","tipo":"societario","simetrico":true,"confianca":"documentado","descricao":"concurso e obra do DNOCS, 1958","periodo":"1958","status":"rascunho"}
{"origem":"paulo-vaz","destino":"eduardo-burle-ferreira","tipo":"societario","simetrico":true,"confianca":"documentado","status":"rascunho"}
{"origem":"marcos-domingues","destino":"carlos-correia-lima","tipo":"coautoria-pontual","confianca":"documentado","descricao":"concurso e projeto do edifício IEP, 1956","periodo":"1956","status":"rascunho"}
{"origem":"mario-russo","destino":"everaldo-gadelha","tipo":"estudo","confianca":"hipotese","descricao":"colega de turma citado sem vínculo explícito","pendencia":"confirmar professores de Gadelha","status":"rascunho"}
{"origem":"acacio-gil-borsoi","destino":"edison-lima","tipo":"estudo","confianca":"hipotese","descricao":"influenciado por seus mestres na EBAP, sem nome específico","pendencia":"identificar professores em currículo ou entrevista","status":"rascunho"}
{"origem":"mario-russo","destino":"paulo-vaz","tipo":"estudo","confianca":"hipotese","descricao":"soluções atribuídas a Russo pela autora; vínculo de sala não nomeado","pendencia":"confirmar matrícula e professores de Paulo Vaz na EBAP","status":"rascunho"}
```

### A.3 depoimentos.jsonl
```jsonl
{"pessoa":"mauricio-castro","existe_escola":false,"argumento":"faltou comunicação de ideias e união profissional entre os arquitetos locais","fonte":{"fonte":"afonso-2008","pagina":"7"},"data_depoimento":"2005-02"}
{"pessoa":"reginaldo-esteves","existe_escola":true,"argumento":"raízes no regionalismo de Gilberto Freyre e na prática de Luiz Nunes, reforçada pelo trabalho de Airton Carvalho","fonte":{"fonte":"afonso-2008"},"data_depoimento":"2005-02"}
{"pessoa":"marcos-domingues","existe_escola":true,"argumento":"soluções funcionais recorrentes: terraços, azulejos, telhados de beiral generoso","fonte":{"fonte":"afonso-2008"},"data_depoimento":"2005-02"}
{"pessoa":"carlos-correia-lima","existe_escola":true,"argumento":"papel central de Delfim Amorim na síntese modernidade + cultura luso-brasileira","fonte":{"fonte":"afonso-2008"},"data_depoimento":"2005-02"}
{"pessoa":"waldeci-pinto","existe_escola":true,"argumento":"Luiz Nunes como precursor, consolidado por Russo, Borsoi e Amorim","fonte":{"fonte":"afonso-2008"},"data_depoimento":"2005-02"}
```

### A.4 Known pendências from the first source
- Everaldo Gadelha: role in the ETCUR team (Russo) mentioned without an explicit verb — decide `trabalho` vs. leave out.
- Luiz Nunes → 1950s masters: historiographic continuity, **not** a documented personal tie. No edge; note on the person.
- Djanira Oiticica: editor of the Delfim Amorim book — researcher, not a network node unless a source shows otherwise.
- Hélio Maia ↔ Heitor Maia Neto: both cousins of Castro; their mutual kinship not stated — `hipotese` if entered.
- Foreign internships of Reginaldo Esteves (Max Bill, Patrix, Vienot): scope decision pending (§12).

### A.5 First simulation results (seed graph, 26 people, 32 relations)
- One connected component of 17 people already emerges from a single source; 7 isolated nodes; Paulo Vaz + Burle Ferreira form a separate 2-node component.
- Highest degree and betweenness: **Reginaldo Esteves and Waldeci Pinto**, not the masters — disciples accumulate `societario` + `mestre-aprendiz` on top of `estudo`, making them structural bridges. Reading: canonical narrative centres on masters; topology centres on the disciples who cross-link. This is the kind of finding only the graph produces.
- Simulated DAC/PE edges for Luiz Nunes created an unconnected 1930s cluster: the 1930s→1950s bridge is missing from the data and must be sought in sources.

---

## Appendix B — Prototype files produced during design

Copy into the repository under `prototypes/` for reference; do not build on them directly except where §7.1 says to port.

- `genealogia-prototipo.html` — Connected-Papers-style graph explorer (D3, embedded data).
- `genealogia-triagem.html` — triage queue UI with 12 real candidates incl. edge cases (keyboard-driven).
- `analisar.py` — first NetworkX analysis script (validation, components, degree, betweenness, export).
- `bibliografia-gap.md` — field bibliography ranked by relation density.
- `conceito-escola-bibliografia.md` — theoretical bibliography and the criteria→metrics table.
