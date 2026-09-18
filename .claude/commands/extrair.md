---
description: Extração assistida (estágio 2 do GAP) sem chave de API — lê os candidatos de uma fonte em lotes, escreve o JSONL de relações, importa e monta a fila de triagem.
---

Fonte alvo: **$ARGUMENTS** (id em `data/fontes.jsonl`, ex.: `porto-2021`). Se vazio, rode `python -m gap status` e escolha a fonte com PDF (`sim`), maior prioridade e coluna `pend.` maior que zero.

Você é o extrator do estágio 2 do GAP (Genealogia da Arquitetura Pernambucana). Leia `CLAUDE.md` antes de começar. Este comando é seguro: você escreve só em `work/<fonte>/` (não versionado); a base `data/*.jsonl` só muda pela triagem humana do Paz.

## Regras de extração (não negociáveis)

Tipos, exatamente estes valores: `heranca` (parentesco: filho/filha, irmãos, primos, casal, cunhados) · `mestre-aprendiz` (aprendizado profissional fora da sala de aula: estágio, convite para equipe, orientação profissional, assistência a professor) · `estudo` (professor → aluno em curso formal) · `trabalho` (emprego/colaboração no escritório, órgão ou equipe de alguém, sem sociedade) · `societario` (sócios em escritório/firma) · `dissidencia` (rompimento) · `coautoria-pontual` (projeto ou concurso em conjunto sem sociedade permanente; "parceria" sem a palavra "sócio").

Direção: em `mestre-aprendiz` e `estudo` a ORIGEM ensina e o DESTINO aprende; em `trabalho` a ORIGEM contrata/coordena; em `dissidencia` a ORIGEM rompe; `heranca` filho: origem = pai/mãe; casal, irmãos, primos e sócios são `simetrico: true`.

1. **Co-menção NÃO é relação.** Duas pessoas na mesma frase sem verbo relacional entre elas → nada.
2. Semelhança de obra, influência estilística, "no espírito de" → nada.
3. Se o texto não afirma claramente, devolva listas vazias. Silêncio é melhor que invenção.
4. `trecho` é cópia **LITERAL** de uma frase do parágrafo-alvo (o em negrito no caderno). A importação rejeita paráfrases.
5. Nenhum conhecimento externo sobre as pessoas. Só o que está no texto.
6. Instituições, cidades, edifícios, obras, empresas NÃO são pessoas.
7. Uma frase pode gerar várias relações ("sócio de A e B, seus primos" → 2 societárias + 2 de parentesco).
8. "Seus professores", "seus mestres" sem nome → nada; registre em `observacao`.
9. Posições de alguém sobre a existência da "Escola do Recife" → `depoimentos`, não `relacoes`.
10. `mencoes_sem_relacao`: pessoas citadas no parágrafo-alvo que não entraram em relação.
11. Nomes copiados como estão no texto; se o contexto vizinho traz a forma completa do mesmo nome, prefira-a. Dados biográficos (datas, cidade natal, formação) vão em `observacao`.
12. `confianca_sugerida`: `documentado` (o texto afirma) · `tradicao_oral` (relato de memória/entrevista sem documento) · `hipotese` (inferência do autor ou sua, ex.: atribuição coletiva a um grupo).
13. Fora do recorte (pessoas sem vínculo com a rede pernambucana, ex.: Lina Bo Bardi, Niemeyer): não crie relações; cite em `observacao`.

## Formato de cada linha do JSONL

```json
{"candidato_id":"porto-2021-p0093-b005","relacoes":[{"origem_nome":"Delfim Amorim","destino_nome":"Heitor Maia Neto","tipo":"societario","subtipo":null,"simetrico":true,"periodo":"1963-1972","descricao":"Heitor Maia Neto foi sócio de Delfim Amorim entre 1963 e 1972.","confianca_sugerida":"documentado","trecho":"com Heitor Maia Neto, seu sócio, entre 1963 e 1972","justificativa":"O texto usa a palavra 'sócio' e dá o período."}],"depoimentos":[],"mencoes_sem_relacao":[],"observacao":null}
```

`periodo` nos formatos `1958`, `1950-1954`, `1964-`, `anos 1960` ou `null`. Candidatos sem relação entram com `"relacoes":[]` — isso os marca como processados. Um arquivo de exemplo é gerado em `work/<fonte>/extraidos_exemplo.jsonl`.

## Procedimento (repita por lotes até `pend.` chegar a zero, ou até 8 lotes por sessão)

1. `python -m gap status <fonte>` — confira `cand.` e `pend.`. Se `cand.` estiver vazio, rode antes `python -m gap chunks <fonte>` e `python -m gap prefilter <fonte>`.
2. `python -m gap export-candidatos <fonte> --pendentes --ordem score --limite 20` — gera `work/<fonte>/caderno.md` só com pendentes, os mais densos primeiro. **Leia apenas esse arquivo.** Nunca abra `chunks.jsonl`, `candidatos.jsonl` ou `prompts.jsonl` inteiros (são grandes).
3. Para cada `## <candidato_id>` do caderno, aplique as regras e escreva uma linha no arquivo `work/<fonte>/extraidos_<modelo>_lote<N>.jsonl` (ex.: `extraidos_claude-haiku_lote3.jsonl`). Copie os `trecho` caractere a caractere do parágrafo em negrito, incluindo erros de OCR.
4. `python -m gap import-extraidos <fonte> <arquivo> --modelo <modelo>` (ex.: `--modelo claude-haiku-4-5`). Se a saída listar `invalidos` (esquema ou "trecho não literal") ou `candidatos_desconhecidos`, corrija **só essas linhas** no arquivo e importe de novo; as válidas já foram gravadas.
5. `python -m gap queue <fonte>` — monta/atualiza a fila de triagem.
6. Volte ao passo 2 com o lote seguinte.

## Ao terminar

Relatório curto para o Paz: lotes feitos; candidatos processados / pendentes; relações e depoimentos propostos; pessoas novas mais frequentes (nomes que não existem na base); pistas registradas em `observacao` (nomes completos, datas, decisões de recorte); lembre que a revisão é dele: `python -m gap triage --fonte <fonte>`.

Não edite `data/*.jsonl` nem `data/vocabularios/*` diretamente. Não faça `git commit` de nada em `work/` (é ignorado). Não use a API Anthropic (`gap extract`) a menos que `ANTHROPIC_API_KEY` esteja definida e o Paz tenha pedido.
