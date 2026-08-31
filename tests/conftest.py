"""Shared test fixtures and helpers."""
from __future__ import annotations

import json

import pytest

from quodeq.data.fs._index_cache import clear_index_cache

# Deep enough to exhaust the C JSON decoder's call stack on a default 8MB
# main-thread stack. ~160KB of text -- trivially producible by hand or by a
# buggy generator, which is what makes this a real degradation path and not a
# curiosity.
_STACK_OVERFLOW_NESTING = 80_000


@pytest.fixture(scope="session")
def deeply_nested_json() -> str:
    """JSON text that makes ``json.loads`` raise ``RecursionError``.

    ``RecursionError`` subclasses ``RuntimeError``, not ``ValueError``, so it
    escapes the ``(OSError, ValueError, UnicodeDecodeError)`` tuple that the
    degrade-to-default config readers catch. Every reader whose contract is
    "a malformed file degrades, it never fails a scan" needs a regression test
    against this payload.

    The depth at which the decoder overflows depends on the interpreter's
    stack size, so the fixture proves the payload really does overflow *this*
    interpreter and skips otherwise. Without that check a build with a deeper
    stack would parse the payload fine and every test using it would pass
    while exercising nothing.
    """
    payload = "[" * _STACK_OVERFLOW_NESTING + "]" * _STACK_OVERFLOW_NESTING
    try:
        json.loads(payload)
    except RecursionError:
        return payload
    pytest.skip(
        f"this interpreter parses {_STACK_OVERFLOW_NESTING} levels of JSON "
        "nesting without overflowing; the RecursionError regression cannot be "
        "exercised here")


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
    # A developer's real custom grade formula (~/.quodeq/grade_formula.json)
    # must never leak into score assertions — 2026-07-31: two rescore-path
    # tests failed machine-locally the moment the Grade Formula Editor saved
    # custom params.
    monkeypatch.setenv("QUODEQ_GRADE_FORMULA_PATH", str(home / "grade_formula.json"))


@pytest.fixture(autouse=True)
def _fresh_index_cache() -> None:
    """Clear the shared project-resolver index cache before every test.

    The cache is a module-level singleton (``data/fs/_index_cache.py``); a
    test that leaves stale mtime-keyed entries in it can leak state into the
    next test that resolves the same path. Suite-wide isolation by default.
    """
    clear_index_cache()
    yield


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


class RecordingLog:
    """A capturing ``quodeq.core.observability.LogSink`` for tests.

    Inner-layer code no longer imports a logging framework -- it accepts an
    injected ``log: LogSink``. Tests that used to assert on ``caplog`` or
    patch a module-level ``log_info``/``log_warning`` instead pass this in
    and assert against the recorded messages.
    """

    def __init__(self) -> None:
        self.info_messages: list[str] = []
        self.warning_messages: list[str] = []
        self.debug_messages: list[str] = []
        self.error_messages: list[str] = []
        self.success_messages: list[str] = []

    def info(self, message: str) -> None:
        self.info_messages.append(message)

    def warning(self, message: str) -> None:
        self.warning_messages.append(message)

    def debug(self, message: str) -> None:
        self.debug_messages.append(message)

    def error(self, message: str) -> None:
        self.error_messages.append(message)

    def success(self, message: str) -> None:
        self.success_messages.append(message)


@pytest.fixture
def recording_log() -> RecordingLog:
    return RecordingLog()
