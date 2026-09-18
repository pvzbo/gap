"""GAP — Genealogia da Arquitetura Pernambucana.

Pacote Python com quatro camadas (ver GAP_BRIEF.md §4):

- ``gap.validate``  — esquema (pydantic) e regras de integridade dos JSONL.
- ``gap.ingest``    — funil PDF → chunks → pré-filtro → extração → resolução → dedup.
- ``gap.analysis``  — grafo (NetworkX), pesos, métricas, fatias temporais, exportações.
- ``gap.app``       — aplicação interna de triagem (FastAPI) que grava na base.

Dados em português; código em inglês/português conforme conveniência.
"""

__version__ = "0.1.0"
