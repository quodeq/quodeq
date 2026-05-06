"""Shared test fixtures and helpers."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_quodeq_home(tmp_path_factory: pytest.TempPathFactory,
                         monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect every Quodeq state path at an empty per-test tmp dir.

    Tests have repeatedly written to the developer's real ``~/.quodeq``
    (a stuck ``state=running`` row in ``index.db`` once leaked through and
    the dashboard auto-resumed it as a phantom job). The previous version
    of this fixture set ``QUODEQ_HOME``, which **nothing in the codebase
    reads** — so the defaults in ``shared/_env.py`` continued to fall
    through to ``Path.home() / ".quodeq"``.

    Set the env vars the production code actually consults:
      * ``QUODEQ_INDEX_DB_PATH``    — ``services/filesystem._open_index``
      * ``QUODEQ_EVALUATIONS_DIR``  — ``services/filesystem.list_evaluations`` etc.
      * ``QUODEQ_DIR``              — ``dashboard/_build_npm._quodeq_dir``
    ``QUODEQ_HOME`` is kept for any out-of-tree consumer that may rely on it.
    """
    home = tmp_path_factory.mktemp("quodeq-home")
    monkeypatch.setenv("QUODEQ_HOME", str(home))
    monkeypatch.setenv("QUODEQ_DIR", str(home))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(home / "index.db"))
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(home / "evaluations"))


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
