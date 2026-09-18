"""Commits automáticos a partir da triagem (Camada 1: Git é a fonte da verdade).

Sem Git instalado ou sem repositório inicializado, tudo continua funcionando:
os JSONL são gravados e o commit fica como "pendente" na decisão. Por padrão
o commit vai para o branch atualmente ativo; defina ``GAP_GIT_BRANCH_POR_FONTE=1``
para commitar em ``triage/<fonte-id>`` (fluxo de pull request, GAP_BRIEF §12).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable

_CANDIDATOS_GIT = (
    r"C:\Program Files\Git\cmd\git.exe",
    r"C:\Program Files (x86)\Git\cmd\git.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Git", "cmd", "git.exe"),
    "/usr/bin/git",
    "/usr/local/bin/git",
    "/opt/homebrew/bin/git",
)


def localizar_git() -> str | None:
    """Caminho do executável git, mesmo quando a instalação ainda não entrou no PATH do processo."""
    env = os.environ.get("GIT_PYTHON_GIT_EXECUTABLE")
    if env and Path(env).exists():
        return env
    achado = shutil.which("git")
    if achado:
        return achado
    for c in _CANDIDATOS_GIT:
        if c and Path(c).exists():
            os.environ["GIT_PYTHON_GIT_EXECUTABLE"] = c
            return c
    return None


def repo_disponivel(root: Path):
    if localizar_git() is None:
        return None
    try:
        import git  # type: ignore

        return git.Repo(root, search_parent_directories=False)
    except Exception:  # noqa: BLE001 - ImportError, InvalidGitRepositoryError, GitCommandNotFound...
        return None


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
