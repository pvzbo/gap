import shutil
from pathlib import Path

import pytest

from gap.config import Paths
from gap.store import load_dataset

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def paths_repo() -> Paths:
    return Paths(ROOT)


@pytest.fixture(scope="session")
def ds_repo(paths_repo):
    return load_dataset(paths_repo)


@pytest.fixture
def repo_tmp(tmp_path) -> Paths:
    """Cópia isolada de data/ e tests/gold para testes que escrevem."""
    shutil.copytree(ROOT / "data", tmp_path / "data")
    shutil.copytree(ROOT / "tests" / "gold", tmp_path / "tests" / "gold")
    (tmp_path / "site").mkdir()
    return Paths(tmp_path)
