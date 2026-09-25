"""run_dir_path / ensure_run_dir: the one place QUODEQ_RUN_DIR is resolved.

#10924 split the old ``get_run_dir`` (which always created the directory as
a side effect) into a pure path computation and an explicit mkdir wrapper.
Every current caller writes into or binds a file under this directory (see
the plan's caller table), so they all keep the mkdir via ``ensure_run_dir``;
``run_dir_path`` exists as the pure primitive underneath it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.shared.env_paths import ensure_run_dir, run_dir_path


def test_run_dir_path_default_is_under_home(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert run_dir_path(env={}) == tmp_path / ".quodeq" / "run"


def test_run_dir_path_creates_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    path = run_dir_path(env={})
    assert not path.exists()


def test_run_dir_path_override_is_used_without_creating_it(tmp_path):
    target = tmp_path / "custom-run"
    assert run_dir_path(env={"QUODEQ_RUN_DIR": str(target)}) == target
    assert not target.exists()


def test_run_dir_path_relative_override_is_rejected():
    with pytest.raises(ValueError):
        run_dir_path(env={"QUODEQ_RUN_DIR": "relative/run"})


def test_ensure_run_dir_default_is_under_home_and_created(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert ensure_run_dir(env={}) == tmp_path / ".quodeq" / "run"
    assert (tmp_path / ".quodeq" / "run").is_dir()


def test_ensure_run_dir_override_is_used_and_created(tmp_path):
    target = tmp_path / "custom-run"
    assert ensure_run_dir(env={"QUODEQ_RUN_DIR": str(target)}) == target
    assert target.is_dir()


def test_ensure_run_dir_relative_override_is_rejected():
    with pytest.raises(ValueError):
        ensure_run_dir(env={"QUODEQ_RUN_DIR": "relative/run"})


def test_ensure_run_dir_agrees_with_run_dir_path(tmp_path):
    """ensure_run_dir's path must be exactly run_dir_path's, just created."""
    env = {"QUODEQ_RUN_DIR": str(tmp_path / "agree-run")}
    assert run_dir_path(env=env) == ensure_run_dir(env=env)
