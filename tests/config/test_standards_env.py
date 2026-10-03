"""The evaluators directory honours its env override before touching HOME."""
from pathlib import Path

from quodeq.config.standards_env import evaluators_dir

_KEY = "QUODEQ_EVALUATORS_DIR"


def _home_unavailable() -> Path:
    raise RuntimeError("Could not determine home directory.")


def test_the_override_wins_without_resolving_home(monkeypatch, tmp_path):
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.setattr(Path, "home", staticmethod(_home_unavailable))
    assert evaluators_dir({_KEY: str(tmp_path)}) == tmp_path


def test_without_the_override_the_default_is_under_home(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert evaluators_dir({}) == tmp_path / ".quodeq" / "evaluators"
