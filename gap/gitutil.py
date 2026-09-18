"""Localização do executável git e abertura do repositório.

Módulo neutro (sem dependências de app ou análise) para que tanto a camada de
análise (hash do commit no relatório) quanto a triagem (commits automáticos)
funcionem mesmo quando o git acabou de ser instalado e ainda não está no PATH
do processo.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

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
    """``git.Repo`` da raiz, ou ``None`` se não há git, não há repositório ou algo falhou."""
    if localizar_git() is None:
        return None
    try:
        import git  # type: ignore

        return git.Repo(root, search_parent_directories=False)
    except Exception:  # noqa: BLE001 - ImportError, InvalidGitRepositoryError, GitCommandNotFound...
        return None


def commit_atual(root: Path) -> str | None:
    try:
        repo = repo_disponivel(Path(root))
        if repo is None or not repo.head.is_valid():
            return None
        return repo.head.commit.hexsha[:12]
    except Exception:  # noqa: BLE001
        return None
