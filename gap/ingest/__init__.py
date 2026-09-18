"""Funil de ingestão (GAP_BRIEF.md §5).

Estágio 0  pdf_to_chunks  PDF → parágrafos com página e índice
Estágio 1  prefilter      filtro léxico (nome + gatilho relacional), sem LLM
Estágio 2  extract        extração estruturada com Claude (apenas candidatos)
Estágio 3  resolve        resolução de entidades (rapidfuzz + aliases)
Estágio 4  dedup / fila   deduplicação e montagem da fila de triagem
Estágio 5  gap.app        triagem humana → commit
"""
