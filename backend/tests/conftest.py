"""Shared test fixtures: the real data set and policy, loaded once per test run."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import REPO_ROOT, Settings
from app.data.loader import POLICY_FILE, load_dataset
from app.policy.parser import load_policy

DATA_DIR = REPO_ROOT / "data"


@pytest.fixture(scope="session")
def dataset():
    return load_dataset(DATA_DIR)


@pytest.fixture(scope="session")
def policy():
    return load_policy(DATA_DIR / POLICY_FILE)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings with a dummy key and a throw-away log folder."""
    return Settings(key_1="test-key", data_dir=DATA_DIR, log_dir=tmp_path / "logs")
