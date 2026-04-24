# tests/shared/test_run_log.py
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from quodeq.shared.run_log import RunLogWriter, RunLogHandler


def test_write_creates_file_with_line(tmp_path: Path) -> None:
    writer = RunLogWriter(tmp_path)
    writer.write("hello")
    writer.close()
    assert (tmp_path / "run.log").read_text() == "hello\n"


def test_write_preserves_existing_newline(tmp_path: Path) -> None:
    writer = RunLogWriter(tmp_path)
    writer.write("already-newlined\n")
    writer.close()
    assert (tmp_path / "run.log").read_text() == "already-newlined\n"


def test_write_is_line_buffered(tmp_path: Path) -> None:
    writer = RunLogWriter(tmp_path)
    writer.write("first")
    # Read back without closing — flush should have happened.
    assert (tmp_path / "run.log").read_text() == "first\n"
    writer.close()


def test_silent_on_missing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    writer = RunLogWriter(missing)  # must not raise
    writer.write("ignored")  # must not raise
    writer.close()
    assert not (missing / "run.log").exists()


def test_path_property(tmp_path: Path) -> None:
    writer = RunLogWriter(tmp_path)
    assert writer.path == tmp_path / "run.log"
    writer.close()


def test_handler_forwards_log_record(tmp_path: Path) -> None:
    writer = RunLogWriter(tmp_path)
    handler = RunLogHandler(writer)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("test.run_log.1")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.info("message-a")
    logger.removeHandler(handler)
    writer.close()
    assert (tmp_path / "run.log").read_text() == "message-a\n"


def test_handler_never_raises_on_format_error(
    tmp_path: Path, no_raise_logging_exceptions: None
) -> None:
    writer = RunLogWriter(tmp_path)
    handler = RunLogHandler(writer)
    logger = logging.getLogger("test.run_log.2")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    # %d on a string arg — format-time error, must not propagate.
    logger.info("%d", "not-an-int")
    logger.removeHandler(handler)
    writer.close()


def test_write_after_close_is_silent_noop(tmp_path: Path) -> None:
    """Closing the writer then calling write() must not raise AttributeError.

    Before the fix, the pre-lock ``if self._fh is None`` caught the serial
    case, but a write() racing with close() could acquire the lock after
    close() nulled out _fh, then hit ``None.write(text)`` and raise.
    After the fix, the None-check lives INSIDE the lock.
    """
    writer = RunLogWriter(tmp_path)
    writer.close()
    # Serial case — always worked. Kept for regression coverage.
    writer.write("after close")
    # After the in-lock check, simulate the race: _fh already non-None in
    # the pre-lock read (stale view), but None by the time we acquire the
    # lock. Force that state directly.
    writer2 = RunLogWriter(tmp_path)
    # Monkey-set _fh to None WITHOUT going through close() — this mimics the
    # race where another thread has nulled _fh while we were queued on the lock.
    writer2._fh = None  # type: ignore[assignment]
    # Must not raise.
    writer2.write("racy write")


def test_concurrent_write_and_close_does_not_raise(tmp_path: Path) -> None:
    """Stress test the check-then-act race: one thread writes in a hot loop
    while another closes. With the fix, no thread raises; without it,
    AttributeError would eventually surface on None.write()."""
    writer = RunLogWriter(tmp_path)

    errors: list[BaseException] = []
    stop = threading.Event()

    def writer_loop() -> None:
        # Keep writing until told to stop; record any exception.
        while not stop.is_set():
            try:
                writer.write("hot-loop line")
            except BaseException as e:  # noqa: BLE001 — we WANT to catch everything here
                errors.append(e)
                return

    t = threading.Thread(target=writer_loop, daemon=True)
    t.start()
    # Give the writer thread a moment to ramp up, then close from main thread.
    time.sleep(0.01)
    writer.close()
    stop.set()
    t.join(timeout=2.0)

    assert errors == [], f"concurrent write/close raised: {errors!r}"


def test_context_manager_closes_on_exit(tmp_path: Path) -> None:
    """RunLogWriter supports the context-manager protocol for safe cleanup."""
    with RunLogWriter(tmp_path) as writer:
        writer.write("inside context")
        # Internal handle is open during the block.
        assert writer._fh is not None  # type: ignore[attr-defined]
    # After exit, the handle is closed.
    assert writer._fh is None  # type: ignore[attr-defined]
    # File contents survive.
    assert "inside context" in (tmp_path / "run.log").read_text()


def test_context_manager_closes_on_exception(tmp_path: Path) -> None:
    """If the with-body raises, the writer still closes."""
    writer = RunLogWriter(tmp_path)
    try:
        with writer:
            writer.write("before raise")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert writer._fh is None  # type: ignore[attr-defined]
    assert "before raise" in (tmp_path / "run.log").read_text()
