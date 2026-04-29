"""Shared test fixtures and helpers."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_quodeq_home(tmp_path_factory: pytest.TempPathFactory,
                         monkeypatch: pytest.MonkeyPatch) -> None:
    """Point QUODEQ_HOME at an empty per-test tmp dir.

    Prevents tests from reading or writing the developer's real
    ``~/.quodeq`` (notably the global ``index.db``, which a Task-12
    ``list_runs`` index-first lookup would otherwise consult).
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
