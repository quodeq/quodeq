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
      * ``QUODEQ_CACHE_ROOT``       — ``analysis/cache/local.default_cache_root``
        (and the online cache). Without this, the content-addressed result
        cache falls through to the real ``~/.quodeq/cache``; the one-time
        legacy-entry GC would then walk and delete from the developer's real
        cache whenever a test reaches the ``cache is None`` production path.
        Sandbox it so the suite is safe by construction, not by per-test
        discipline.
    ``QUODEQ_HOME`` is kept for any out-of-tree consumer that may rely on it.
    """
    home = tmp_path_factory.mktemp("quodeq-home")
    monkeypatch.setenv("QUODEQ_HOME", str(home))
    monkeypatch.setenv("QUODEQ_DIR", str(home))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(home / "index.db"))
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(home / "evaluations"))
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(home / "cache"))
    # Belt-and-braces: _default_persist_dir now derives from the index-db
    # parent, but tests that build a JobManager without a store must never
    # touch the real ~/.quodeq/run/jobs again (it was wedged with fake jobs
    # named job-wire/sample-project that surfaced in the real dashboard).
    monkeypatch.setenv("QUODEQ_JOB_PERSIST_DIR", str(home / "run" / "jobs"))


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
