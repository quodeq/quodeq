"""Shared test fixtures and helpers."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_quodeq_home(tmp_path_factory: pytest.TempPathFactory,
                         monkeypatch: pytest.MonkeyPatch) -> None:
    """Point QUODEQ_HOME at an empty per-test tmp dir.

    Defensive isolation so tests cannot accidentally read or write the
    developer's real ``~/.quodeq`` (which holds the existing global
    ``index.db`` from ``services/run_index.py``, plus per-run state).
    """
    home = tmp_path_factory.mktemp("quodeq-home")
    monkeypatch.setenv("QUODEQ_HOME", str(home))


class DummyProcess:
    """Minimal process stub for tests that need a mock subprocess."""

    def __init__(self):
        self._returncode = 0

    def wait(self):
        return self._returncode

    def poll(self):
        return self._returncode

    def terminate(self):
        pass


@pytest.fixture
def dummy_process():
    """Return a DummyProcess instance."""
    return DummyProcess()
