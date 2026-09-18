# GAP — instruções para o Claude Code

Leia `GAP_BRIEF.md` antes de qualquer alteração: é a fonte única de decisões de projeto (pergunta de pesquisa, esquema, funil, métricas, padrões). `README.md` tem os comandos.

## Regras que o código deve preservar
- Dados em português (campos, tipos de relação, descrições). UI em português. Código pode ser em inglês.
- **Nunca invente relações nem fatos sobre pessoas.** Tudo vem de fonte com página e trecho; sem fonte só `hipotese` com `pendencia`.
- `peso` nunca é gravado: fórmula única em `gap/analysis/weights.py` (versionada).
- Ids são permanentes; variantes de nome vão para `data/vocabularios/aliases.yaml`.
- Nomes de instituições em `atuacao`/`formacao` devem existir em `data/vocabularios/instituicoes.yaml`.
- Relações (linhas) ≠ arestas (pares únicos). Não confundir nas contagens.
- Novo tipo de relação só quando um `subtipo` recorrer 3+ vezes (GAP_BRIEF §2).
- `raw_pdfs/`, `work/`, `export/`, `site/data/` não são versionados. `extracoes/<fonte>/extraidos.jsonl` é versionado: propostas pré-triagem com trechos curtos (`gap salvar-extracao` / `gap restaurar-extracao`).

## Comandos úteis
```
python -m gap validate            # deve terminar com 0 erro(s)
python -m pytest -q               # suíte completa (~10 s)
python -m gap build               # regenera export/ e site/data/
python -m gap triage              # app interno (FastAPI) em :8765; /site/ serve o site público
python -m gap status              # estado do funil por fonte
```
Use `python -m gap` (o executável `gap` pode não estar no PATH no Windows). Caminhos sempre via `pathlib`.

## Onde está cada coisa
- Esquema pydantic e regras de CI: `gap/validate/`
- Funil: `gap/ingest/` (chunks → prefilter → extract → resolve → dedup/fila → benchmark)
- Métricas e exportações: `gap/analysis/` (`metrics.relatorio` é o relatório completo)
- App de triagem: `gap/app/` (`actions.Editor` faz as mutações; toda decisão tem `efeitos` reversíveis)
- Site: `site/js/app.js` lê `site/data/grafo.json` (gerado)
- Gold standard: `tests/gold/afonso-2008/relacoes_gold.jsonl`

## Extração com Claude (estágio 2)
Dois caminhos, mesma saída (`work/<fonte>/extraidos.jsonl`), mesma triagem depois:
- **API** (`gap extract`): modelo padrão `claude-haiku-4-5`; escalonamento `claude-sonnet-5`. Prompt conservador em `gap/ingest/extract.py`. Saída estruturada via `client.messages.parse(..., output_format=ExtracaoChunk)`. Exige `ANTHROPIC_API_KEY` ou perfil `ant auth login`; sem credencial aborta antes de chamar.
- **Assistida, sem chave** (`/extrair <fonte>` — comando em `.claude/commands/extrair.md`): a própria sessão do Claude Code lê `work/<fonte>/caderno.md` em lotes de ~20 (`gap export-candidatos <fonte> --pendentes --ordem score --limite 20`), escreve o JSONL e importa com `gap import-extraidos` (rejeita `trecho` não literal). Regras completas no comando. Use `python -m gap status` para ver `pend.` por fonte.

Ordem sugerida das fontes locais: `porto-2021` (em andamento), `silva-2020`, `lamour-filho-2023`, `feitosa-2023`, `reynaldo-2013`, depois as demais de `data/fontes.jsonl` com PDF.

## Decisões abertas (perguntar ao Paz quando bloquearem)
Ver GAP_BRIEF §12: figuras estrangeiras como nós; 8º tipo `equipe-institucional`; branch por fonte vs. main; app interno e site como um ou dois códigos; identidade visual própria.
