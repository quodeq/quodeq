"""Shared test fixtures and helpers."""
from __future__ import annotations

import json
import os
from collections.abc import Iterator

import pytest
from unittest import mock

from quodeq.data.cache_store.index import close_all_for_tests
from quodeq.data.fs._index_cache import clear_index_cache
from quodeq.services.score_cache import clear_stale_payloads

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
def _env_leak_guard() -> Iterator[None]:
    """Fail any test that leaves os.environ different from how it found it.

    Set env through ``monkeypatch.setenv`` / ``monkeypatch.delenv`` (undone
    before this teardown runs) or ``unittest.mock.patch.dict``; a bare
    ``os.environ[...] = ...`` in one test silently reconfigures every test
    that runs after it in the same process.
    """
    # pytest rewrites PYTEST_CURRENT_TEST for every phase (setup/call/teardown).
    before = {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}
    yield
    after = {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    assert not (added or removed or changed), (
        "Test leaked os.environ changes; use monkeypatch.setenv/delenv, or request "
        "the restore_environ fixture when the code under test sets variables itself.\n"
        f"  added: {added}\n  removed: {removed}\n  changed: {changed}"
    )


@pytest.fixture
def restore_environ() -> Iterator[None]:
    """Restore os.environ wholesale after the test.

    For tests whose code under test adds variables itself (PYTHONUTF8 from
    configure_stdio_utf8, QUODEQ_WEBVIEW_TOKEN from the dashboard server).
    monkeypatch cannot undo a key that was absent at setup, patch.dict can.
    """
    with mock.patch.dict(os.environ):
        yield


@pytest.fixture(autouse=True)
def _isolate_quodeq_home(tmp_path_factory: pytest.TempPathFactory,
                         monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect every Quodeq state path at an empty per-test tmp dir.

    Tests have repeatedly written to the developer's real ``~/.quodeq``
    (a stuck ``state=running`` row in ``index.db`` once leaked through and
    the dashboard auto-resumed it as a phantom job). The previous version
    of this fixture set ``QUODEQ_HOME``, which **nothing in the codebase
    reads** — so the defaults in ``shared/env.py`` continued to fall
    through to ``Path.home() / ".quodeq"``.

    Set the env vars the production code actually consults:
      * ``QUODEQ_INDEX_DB_PATH``    — ``services/filesystem._open_index``
      * ``QUODEQ_EVALUATIONS_DIR``  — ``services/filesystem.list_evaluations`` etc.
      * ``QUODEQ_DIR``              — ``dashboard/_build_npm.quodeq_dir``
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


@pytest.fixture(autouse=True)
def _fresh_stale_payloads() -> None:
    """Clear the accumulated stale-while-revalidate slots before every test.

    Module-level like the index cache (``services/_score_cache_stale.py``), and
    keyed by project name, so a payload from one test would be served as
    "stale" to the next test that reuses the name.
    """
    clear_stale_payloads()
    yield


@pytest.fixture(autouse=True)
def _close_content_indexes() -> None:
    """Close every ``ContentIndex`` sqlite connection opened during the test.

    ``QUODEQ_CACHE_ROOT`` points at a fresh tmp dir per test (see
    ``_isolate_quodeq_home``), so most tests that touch cache code open a
    distinct ``.index.db`` connection that nothing explicitly closes --
    production code relies on the process exiting to release it. In one
    long single-process test run those connections pile up faster than GC
    reclaims them (worse under coverage instrumentation), and file
    descriptor numbers climb past 1024, which breaks unrelated
    ``select()``-based PTY tests. Close them all after each test instead.
    """
    yield
    close_all_for_tests()


@pytest.fixture(autouse=True)
def _reset_cancellation() -> None:
    """Clear the process-wide cancellation token before and after every test.

    Global and autouse rather than opt-in (#1201): the token is a single
    process-wide flag (``quodeq/shared/cancellation.py``), so a test that
    requests cancellation without restoring it used to leak the cancelled
    state into whatever test ran next in the same process -- the symptom
    surfaced as a scout burst silently taking the cancelled path in an
    unrelated test file, not in the test that set the flag.
    """
    from quodeq.shared import cancellation

    cancellation.reset()
    yield
    cancellation.reset()


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
