# tests/shared/test_run_log.py
from __future__ import annotations

import logging
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
