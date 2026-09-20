"""get_run_dir: the one place QUODEQ_RUN_DIR is resolved."""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.shared.env_paths import get_run_dir


def test_default_is_under_home(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert get_run_dir(env={}) == tmp_path / ".quodeq" / "run"
    assert (tmp_path / ".quodeq" / "run").is_dir()


def test_override_is_used_and_created(tmp_path):
    target = tmp_path / "custom-run"
    assert get_run_dir(env={"QUODEQ_RUN_DIR": str(target)}) == target
    assert target.is_dir()


def test_relative_override_is_rejected():
    with pytest.raises(ValueError):
        get_run_dir(env={"QUODEQ_RUN_DIR": "relative/run"})
