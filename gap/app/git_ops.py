"""Commits automáticos a partir da triagem (Camada 1: Git é a fonte da verdade).

Sem Git instalado ou sem repositório inicializado, tudo continua funcionando:
os JSONL são gravados e o commit fica como "pendente" na decisão. Por padrão
o commit vai para o branch atualmente ativo; defina ``GAP_GIT_BRANCH_POR_FONTE=1``
para commitar em ``triage/<fonte-id>`` (fluxo de pull request, GAP_BRIEF §12).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from ..gitutil import localizar_git, repo_disponivel  # noqa: F401 - reexportados para a app


def commit(root: Path, mensagem: str, arquivos: Iterable[Path], fonte_id: str | None = None) -> str | None:
    repo = repo_disponivel(root)
    if repo is None:
        return None
    try:
        if fonte_id and os.environ.get("GAP_GIT_BRANCH_POR_FONTE") == "1":
            nome = f"triage/{fonte_id}"
            if repo.active_branch.name != nome:
                if nome in [h.name for h in repo.heads]:
                    repo.heads[nome].checkout()
                else:
                    repo.create_head(nome).checkout()
        rel = []
        for a in arquivos:
            a = Path(a)
            if a.exists():
                rel.append(str(a.resolve().relative_to(Path(root).resolve())).replace("\\", "/"))
        if not rel:
            return None
        repo.index.add(rel)
        if not repo.index.diff("HEAD") and not repo.untracked_files:
            return None
        c = repo.index.commit(mensagem)
        return c.hexsha[:12]
    except Exception:  # noqa: BLE001
        return None


def estado(root: Path) -> dict:
    repo = repo_disponivel(root)
    if repo is None:
        return {"disponivel": False, "branch": None, "commit": None, "sujo": None}
    try:
        return {
            "disponivel": True,
            "branch": repo.active_branch.name if not repo.head.is_detached else "(detached)",
            "commit": repo.head.commit.hexsha[:12] if repo.head.is_valid() else None,
            "sujo": repo.is_dirty(untracked_files=True),
        }
    except Exception:  # noqa: BLE001
        return {"disponivel": True, "branch": None, "commit": None, "sujo": None}
