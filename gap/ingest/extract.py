"""Estágio 2 — extração estruturada com Claude (GAP_BRIEF.md §5, estágio 2).

Só os candidatos do pré-filtro chegam aqui, cada um com os parágrafos vizinhos
(anáfora). O prompt é explicitamente conservador: co-menção não é relação;
devolver lista vazia quando nada é afirmado; ``trecho`` literal obrigatório.

Modelo padrão: Claude Haiku 4.5 (barato; volume pequeno após o pré-filtro).
Escalonamento para Claude Sonnet 5 apenas nos candidatos marcados como ambíguos
na triagem (``--modelo`` + ``--ids``).

Saída: ``work/<fonte>/extraidos.jsonl`` — uma linha por candidato, com as
propostas de relação/depoimento e ``mencoes_sem_relacao``. Retomável: candidatos
já extraídos são pulados, salvo ``--refazer``.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..config import MODELO_EXTRACAO, Paths, TIPOS_RELACAO
from ..store import Dataset, read_jsonl, write_jsonl


class CredencialAusente(RuntimeError):
    """Sem forma de autenticar na API Anthropic."""


class ExtracaoInterrompida(RuntimeError):
    """Falhas consecutivas: provável problema de rede, modelo ou cota — não de um chunk específico."""


MENSAGEM_CREDENCIAL = (
    "Sem credencial da API Anthropic. No PowerShell: setx ANTHROPIC_API_KEY \"sua-chave\" e abra um NOVO terminal "
    "(ou, só para a sessão atual: $env:ANTHROPIC_API_KEY = \"sua-chave\"). Alternativa: `ant auth login`. "
    "Use --dry-run para gerar os prompts sem chamar a API."
)

MAX_FALHAS_CONSECUTIVAS = 3


def credencial_disponivel() -> bool:
    """Verificação local (sem rede): variável de ambiente ou perfil do `ant auth login`."""
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    perfil = Path(os.environ.get("ANTHROPIC_CONFIG_DIR") or (Path.home() / ".config" / "anthropic"))
    try:
        return perfil.is_dir() and any(perfil.iterdir())
    except OSError:
        return False


def eh_erro_de_credencial(exc: BaseException) -> bool:
    nome = type(exc).__name__.lower()
    msg = str(exc).lower()
    return (
        "authentication" in nome
        or "permissiondenied" in nome
        or "authentication" in msg
        or "api_key" in msg
        or "api key" in msg
        or "credential" in msg
    )


# --------------------------------------------------------------------------- #
# Esquema de saída (structured outputs)
# --------------------------------------------------------------------------- #

class RelacaoExtraida(BaseModel):
    origem_nome: str = Field(description="Nome da pessoa de origem exatamente como aparece no texto (ou o nome mais completo presente no trecho/contexto).")
    destino_nome: str = Field(description="Nome da pessoa de destino exatamente como aparece no texto.")
    tipo: Literal["heranca", "mestre-aprendiz", "estudo", "trabalho", "societario", "dissidencia", "coautoria-pontual"]
    subtipo: str | None = Field(default=None, description="Especificação livre, ex.: 'primos', 'esposa', 'concurso', 'estágio'.")
    simetrico: bool = Field(description="true quando a relação não tem direção intrínseca (sócios, coautores, primos).")
    periodo: str | None = Field(default=None, description="Ano ou intervalo afirmado no texto, formatos: '1954', '1950-1954', '1964-'. null se não houver.")
    descricao: str = Field(description="Uma frase, em português, resumindo o vínculo conforme o texto.")
    confianca_sugerida: Literal["documentado", "tradicao_oral", "hipotese"] = Field(description="'documentado' se o texto afirma o vínculo; 'tradicao_oral' se relata depoimento/memória sem documento; 'hipotese' se é inferência do autor ou sua.")
    trecho: str = Field(description="Frase LITERAL do texto (copiada, sem parafrasear) que fundamenta a relação.")
    justificativa: str = Field(description="Por que este trecho estabelece o vínculo (uma frase).")


class DepoimentoExtraido(BaseModel):
    pessoa_nome: str
    existe_escola: bool | None = Field(description="true se afirma que a Escola do Recife existiu; false se nega; null se ambíguo.")
    argumento: str
    trecho: str


class ExtracaoChunk(BaseModel):
    relacoes: list[RelacaoExtraida] = Field(default_factory=list)
    depoimentos: list[DepoimentoExtraido] = Field(default_factory=list)
    mencoes_sem_relacao: list[str] = Field(default_factory=list, description="Nomes de pessoas citados no parágrafo-alvo sem relação identificável com outra pessoa.")
    observacao: str | None = Field(default=None, description="Dúvidas ou ambiguidades relevantes para a triagem humana.")


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = """Você extrai RELAÇÕES DOCUMENTADAS ENTRE PESSOAS de textos acadêmicos sobre a arquitetura de Pernambuco (Brasil, século XX), para o projeto GAP — Genealogia da Arquitetura Pernambucana.

Você recebe um parágrafo-alvo com os parágrafos vizinhos como contexto. Devolva apenas o que o PARÁGRAFO-ALVO afirma (use os vizinhos só para resolver pronomes e nomes incompletos).

Tipos de relação (use exatamente estes valores):
- heranca: parentesco (filho/filha, irmão, primos, casal, cunhados).
- mestre-aprendiz: aprendizado profissional fora da sala de aula (estágio, convite para equipe, orientação profissional, primeiro emprego com um profissional).
- estudo: relação professor → aluno em curso formal.
- trabalho: emprego/colaboração no escritório, órgão ou equipe de alguém, sem sociedade.
- societario: sócios em escritório/firma.
- dissidencia: rompimento, saída, ruptura entre pessoas.
- coautoria-pontual: projeto/concurso feito em conjunto, sem sociedade permanente.

Direção: em mestre-aprendiz e estudo a ORIGEM é quem ensina/orienta e o DESTINO é quem aprende. Em heranca, origem e destino podem ser trocados livremente quando simétrico (primos, casal); em "filho de", origem = pai/mãe. Em trabalho, ORIGEM é quem contrata/coordena, DESTINO quem trabalha para. Em dissidencia, ORIGEM é quem rompe.

REGRAS OBRIGATÓRIAS:
1. Co-menção NÃO é relação. Duas pessoas citadas na mesma frase sem verbo relacional entre elas → nada.
2. Semelhança de obra, influência estilística ou "no espírito de" NÃO é relação. Só vínculo pessoal afirmado.
3. Quando o texto não afirma claramente um vínculo, devolva listas vazias. Silêncio é melhor que invenção.
4. `trecho` é cópia LITERAL de uma frase do parágrafo-alvo. Nunca parafraseie.
5. Não use conhecimento externo sobre as pessoas. Só o que está no texto.
6. Instituições, cidades, edifícios, obras e empresas NÃO são pessoas. Não crie relações com eles.
7. Uma frase pode gerar várias relações (ex.: "sócio de A e B, seus primos" → 4 relações: 2 societárias + 2 de parentesco).
8. Menções genéricas ("seus professores", "seus mestres") sem nome NÃO geram relação; registre em `observacao`.
9. Posições sobre a existência da "Escola do Recife" (afirmar/negar que houve uma escola) vão em `depoimentos`, não em `relacoes`.
10. `mencoes_sem_relacao`: nomes de pessoas (não instituições) presentes no parágrafo-alvo que não entraram em nenhuma relação.
11. Nomes de pessoas devem ser copiados como estão no texto; se o contexto vizinho traz a forma completa do mesmo nome, prefira a forma completa.
"""


def montar_mensagem(cand: dict[str, Any], fonte: dict[str, Any]) -> str:
    conhecidos = sorted({n.get("variante", "") for n in cand.get("nomes_conhecidos") or []})
    desconhecidos = cand.get("nomes_desconhecidos") or []
    dicas = ""
    if conhecidos or desconhecidos:
        dicas = (
            "\n\nNomes detectados automaticamente no parágrafo-alvo (apenas pistas; não invente vínculos para eles): "
            + "; ".join(conhecidos + list(desconhecidos))
        )
    ref = f"{fonte.get('autor') or ''} — {fonte.get('titulo') or fonte.get('id')} ({fonte.get('ano') or 's.d.'})".strip(" —")
    return (
        f"FONTE: {ref}\nPÁGINA: {cand.get('pagina')}\n\n"
        f"[CONTEXTO ANTERIOR]\n{cand.get('contexto_anterior') or '(nenhum)'}\n\n"
        f"[PARÁGRAFO-ALVO]\n{cand.get('texto')}\n\n"
        f"[CONTEXTO POSTERIOR]\n{cand.get('contexto_posterior') or '(nenhum)'}"
        f"{dicas}"
    )


# --------------------------------------------------------------------------- #
# Chamada ao modelo
# --------------------------------------------------------------------------- #

def _extrair_json(texto: str) -> dict[str, Any]:
    texto = texto.strip()
    m = re.search(r"\{.*\}", texto, re.S)
    if not m:
        raise ValueError("resposta sem JSON")
    return json.loads(m.group(0))


def chamar_modelo(client: Any, modelo: str, mensagem: str, *, max_tokens: int = 4096) -> tuple[ExtracaoChunk, dict[str, Any]]:
    """Chama Claude com saída estruturada; cai para JSON livre se o modelo recusar o formato."""
    import anthropic

    system = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
    messages = [{"role": "user", "content": mensagem}]
    try:
        resp = client.messages.parse(
            model=modelo,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            output_format=ExtracaoChunk,
        )
        parsed: ExtracaoChunk | None = getattr(resp, "parsed_output", None)
        if parsed is None:  # pragma: no cover - defesa
            texto = next((b.text for b in resp.content if b.type == "text"), "")
            parsed = ExtracaoChunk.model_validate(_extrair_json(texto))
    except anthropic.BadRequestError as exc:
        if "output_format" not in str(exc) and "output_config" not in str(exc) and "format" not in str(exc):
            raise
        resp = client.messages.create(
            model=modelo,
            max_tokens=max_tokens,
            system=system + [{"type": "text", "text": "Responda APENAS com um objeto JSON válido com as chaves: relacoes, depoimentos, mencoes_sem_relacao, observacao."}],
            messages=messages,
        )
        texto = next((b.text for b in resp.content if b.type == "text"), "")
        parsed = ExtracaoChunk.model_validate(_extrair_json(texto))
    uso = {
        "input_tokens": getattr(resp.usage, "input_tokens", None),
        "output_tokens": getattr(resp.usage, "output_tokens", None),
        "cache_read_input_tokens": getattr(resp.usage, "cache_read_input_tokens", None),
        "cache_creation_input_tokens": getattr(resp.usage, "cache_creation_input_tokens", None),
    }
    return parsed, uso


def criar_cliente() -> Any:
    import anthropic

    return anthropic.Anthropic()


# --------------------------------------------------------------------------- #
# Orquestração por fonte
# --------------------------------------------------------------------------- #

def extrair_fonte(
    paths: Paths,
    ds: Dataset,
    fonte_id: str,
    *,
    modelo: str = MODELO_EXTRACAO,
    limite: int | None = None,
    ids: set[str] | None = None,
    refazer: bool = False,
    dry_run: bool = False,
    client: Any | None = None,
    progresso: Any | None = None,
) -> dict[str, Any]:
    pasta = paths.work_fonte(fonte_id)
    candidatos = read_jsonl(pasta / "candidatos.jsonl")
    if not candidatos:
        raise FileNotFoundError(f"Sem candidatos para '{fonte_id}'. Rode `gap prefilter {fonte_id}` primeiro.")
    fonte = ds.fontes_por_id.get(fonte_id, {"id": fonte_id})

    candidatos.sort(key=lambda c: (-float(c.get("score") or 0), c.get("pagina") or 0, c.get("paragrafo") or 0))
    if ids:
        candidatos = [c for c in candidatos if c["chunk_id"] in ids]

    arq = pasta / "extraidos.jsonl"
    existentes = {r["candidato_id"]: r for r in read_jsonl(arq)}
    if not refazer and not ids:
        # linhas com `erro` contam como não extraídas: são refeitas por padrão
        candidatos = [c for c in candidatos if c["chunk_id"] not in existentes or existentes[c["chunk_id"]].get("erro")]
    if limite is not None:
        candidatos = candidatos[:limite]

    if dry_run:
        write_jsonl(
            pasta / "prompts_dry_run.jsonl",
            ({"candidato_id": c["chunk_id"], "modelo": modelo, "system": SYSTEM_PROMPT, "user": montar_mensagem(c, fonte)} for c in candidatos),
        )
        return {"fonte": fonte_id, "modelo": modelo, "dry_run": True, "n_prompts": len(candidatos), "arquivo": str(pasta / "prompts_dry_run.jsonl")}

    if not candidatos:
        return {"fonte": fonte_id, "modelo": modelo, "n_processados": 0, "n_relacoes": 0, "n_depoimentos": 0, "n_erros": 0, "mensagem": "nada novo a extrair"}

    if client is None and not credencial_disponivel():
        raise CredencialAusente(MENSAGEM_CREDENCIAL)
    client = client or criar_cliente()
    n_rel = n_dep = n_err = 0
    tokens_in = tokens_out = 0
    falhas_seguidas = 0
    ultimo_erro: str | None = None
    for i, c in enumerate(candidatos, start=1):
        linha: dict[str, Any] = {
            "candidato_id": c["chunk_id"],
            "pagina": c.get("pagina"),
            "modelo": modelo,
            "extraido_em": _dt.datetime.now().isoformat(timespec="seconds"),
        }
        try:
            parsed, uso = chamar_modelo(client, modelo, montar_mensagem(c, fonte))
            linha.update(parsed.model_dump())
            linha["uso"] = uso
            n_rel += len(parsed.relacoes)
            n_dep += len(parsed.depoimentos)
            tokens_in += uso.get("input_tokens") or 0
            tokens_out += uso.get("output_tokens") or 0
            falhas_seguidas = 0
        except Exception as exc:  # noqa: BLE001
            if eh_erro_de_credencial(exc):
                # não persiste: nada foi extraído e o problema não é do chunk
                raise CredencialAusente(f"{MENSAGEM_CREDENCIAL} (erro da API: {type(exc).__name__}: {exc})") from exc
            ultimo_erro = f"{type(exc).__name__}: {exc}"
            linha.update({"relacoes": [], "depoimentos": [], "mencoes_sem_relacao": [], "observacao": None, "erro": ultimo_erro})
            n_err += 1
            falhas_seguidas += 1
        existentes[c["chunk_id"]] = linha
        write_jsonl(arq, existentes.values())  # grava a cada passo: retomável
        if progresso:
            progresso(i, len(candidatos), linha)
        if falhas_seguidas >= MAX_FALHAS_CONSECUTIVAS:
            raise ExtracaoInterrompida(
                f"Extração interrompida após {falhas_seguidas} falhas consecutivas (rede, modelo ou cota?). "
                f"Último erro: {ultimo_erro}. As linhas com erro serão refeitas na próxima execução."
            )

    return {
        "fonte": fonte_id,
        "modelo": modelo,
        "n_processados": len(candidatos),
        "n_relacoes": n_rel,
        "n_depoimentos": n_dep,
        "n_erros": n_err,
        "tokens_entrada": tokens_in,
        "tokens_saida": tokens_out,
        "arquivo": str(arq),
    }


def carregar_extraidos(paths: Paths, fonte_id: str) -> list[dict[str, Any]]:
    return read_jsonl(paths.work_fonte(fonte_id) / "extraidos.jsonl")


TIPOS_VALIDOS = set(TIPOS_RELACAO)
