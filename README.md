# GAP — Genealogia da Arquitetura Pernambucana

Instrumento de pesquisa que mapeia a rede de pessoas que fizeram a arquitetura de Pernambuco no último século — arquitetos, urbanistas, professores e engenheiros com atribuição arquitetônica — como um grafo de relações documentadas (parentesco, mestre–aprendiz, estudo, trabalho, sociedade, dissidência, coautoria). Objetivo científico: testar, com evidência quantitativa, se a chamada **"Escola do Recife"** existiu como escola. Objetivo operacional: uma base que cresce a cada fonte processada, com proveniência e confiança em cada aresta, e um site que permite explorar a rede.

O documento de referência é **[GAP_BRIEF.md](GAP_BRIEF.md)** — leia-o antes de mexer em dados ou código.

## Arquitetura em uma linha

```
raw_pdfs/ → gap chunks → gap prefilter → gap extract (Claude) → gap queue → gap triage (humano) → data/*.jsonl (Git) → gap build → export/ + site/
```

| Camada | Onde | O quê |
|---|---|---|
| 0 — funil de ingestão | `gap/ingest/` | PDF → parágrafos com página → pré-filtro léxico → extração estruturada → resolução de entidades → dedup → fila |
| 1 — fonte da verdade | `data/*.jsonl`, `data/vocabularios/*.yaml` | pessoas, relações, depoimentos, fontes; instituições e variantes de nome. Cada mudança é um commit |
| 2 — análise | `gap/analysis/` | NetworkX: pesos, centralidades, comunidades, subgrafos por tipo, auditoria de confiança, fatias por década, exportações |
| 3 — apresentação | `site/` | site estático (D3) que lê `site/data/grafo.json`: rede, ego-rede, página de pessoa, filtros por instituição, métricas |
| app interno | `gap/app/` | painel de fontes + triagem por teclado (FastAPI); grava nos JSONL e commita quando há Git |

## Começando

Requisitos: Python 3.11+. Git é recomendado (fonte da verdade e commits automáticos da triagem), mas tudo funciona sem ele.

```bash
python -m pip install -e .
python -m gap validate          # regras de integridade (CI roda isto em cada PR)
python -m gap build             # grafo → métricas → export/ e site/data/
python -m gap site              # abre o site em http://127.0.0.1:8080/
python -m gap triage            # app interno em http://127.0.0.1:8765/
```

`pip install -e .` também instala o executável `gap`; no Windows ele fica em `%LOCALAPPDATA%\Programs\Python\Python313\Scripts` — adicione essa pasta ao PATH ou use sempre `python -m gap`.

### Processar uma fonte

```bash
python -m gap inventory                      # registra PDFs de raw_pdfs/ em data/fontes.jsonl
python -m gap chunks porto-2021              # estágio 0
python -m gap prefilter porto-2021           # estágio 1 (sem LLM)
python -m gap extract porto-2021 --limite 30 # estágio 2 — exige ANTHROPIC_API_KEY (ou `ant auth login`)
python -m gap queue porto-2021               # estágios 3–4
python -m gap triage --fonte porto-2021      # estágio 5 — triagem humana
python -m gap benchmark afonso-2008 --detalhes  # compara com tests/gold/
python -m gap status                         # estado do funil por fonte
```

`gap ingest <fonte|arquivo.pdf> [--extract]` encadeia os estágios. Todos os intermediários ficam em `work/<fonte-id>/` (não versionado). A extração usa Claude Haiku 4.5 por padrão; escalone casos ambíguos com `--modelo claude-sonnet-5 --ids <chunk_id,...>`. `--dry-run` grava os prompts sem chamar a API.

### Triagem

Atalhos: **A** aceitar · **D** descartar · **S** adiar · **Z** desfazer · **1–7** tipo · **X** trocar origem/destino. Cada aceite grava em `data/relacoes.jsonl` (ou anexa a fonte a uma relação já existente do mesmo par e tipo), aprende variantes de nome em `aliases.yaml`, registra a decisão em `work/<fonte>/decisoes.jsonl` e, com Git disponível, faz um commit. A entrada manual (relação que o leitor infere e a máquina não) e a criação de pessoas ficam na coluna direita. Defina `GAP_GIT_BRANCH_POR_FONTE=1` para commitar em `triage/<fonte>` em vez do branch atual.

## Layout

```
data/                    fonte da verdade (JSONL + YAML)
gap/                     pacote Python (config, store, validate/, ingest/, analysis/, app/, cli.py)
site/                    site público estático (index.html, css/, js/; data/ é gerado)
export/                  gerado por `gap build`: grafo.json, pessoas.csv, relacoes.csv, metricas.{json,md}, grafo.{gexf,graphml}, pendencias.md
tests/                   pytest + tests/gold/afonso-2008/ (gold standard)
prototypes/              protótipos da fase de desenho (referência; não construir sobre eles)
raw_pdfs/, work/         corpus local e intermediários (ignorados pelo Git)
.github/workflows/       validação em cada PR; build e publicação do site em push para main
```

## Padrões não negociáveis (GAP_BRIEF §11)

1. Nunca inventar relação: co-menção não é relação. Em dúvida, `hipotese` + `pendencia`, ou nada.
2. Toda aresta tem proveniência (fonte, página, trecho) ou está visivelmente marcada como carente dela.
3. `confianca` (evidência) ≠ `status` (revisão editorial).
4. Fatos sobre pessoas vêm das fontes, não do conhecimento do modelo.
5. Pesos são computados (`gap/analysis/weights.py`), nunca gravados.
6. Ids são permanentes; variantes vão para `aliases.yaml`.
7. Dados em português; código pode ser em inglês.
8. `gap build` a partir de um checkout limpo regenera tudo.
9. Lacunas aparecem: isolados, pontes ausentes e pendências são resultados.
10. Só trechos curtos das fontes; nunca reproduzir passagens longas no site.

## Estado

- Fase 1 (fundação) e Fase 2 (funil + triagem) implementadas; benchmark do pré-filtro em Afonso 2008: 28/28 relações localizáveis recuperadas.
- Corpus local inventariado (19 PDFs); metadados lidos das folhas de rosto — confirmar em `data/fontes.jsonl`.
- Próximos passos: extração com Claude sobre `porto-2021`, `silva-2020`, `lamour-filho-2023`; entrada da equipe da DAC/PE a partir de Vaz 1989 / Naslavsky 1998; decisões abertas em GAP_BRIEF §12.
