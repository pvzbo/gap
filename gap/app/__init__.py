"""Aplicação interna de triagem (GAP_BRIEF.md §5, estágio 5).

FastAPI + templates Jinja2 + JS vanilla. Grava diretamente nos JSONL da pasta
``data/`` e, quando o Git está disponível, faz um commit por decisão.
"""
