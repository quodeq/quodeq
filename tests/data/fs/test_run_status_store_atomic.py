"""status.json is written through a unique temp file and an atomic replace."""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

import pytest

from quodeq.data.fs import run_artifacts
from quodeq.data.fs.run_status_store import RunState, RunStatus, read_status, write_status

_STARTED = "2026-04-20T00:00:00+00:00"
_WRITES_PER_WRITER = 40


def _status(job_id: str) -> RunStatus:
    return RunStatus(state=RunState.RUNNING, job_id=job_id, started_at=_STARTED, dimensions=["security"])


def _failing_dump(fd, tmp_path, path, data, *, indent=None, mode=None):
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write('{"schema_version": ')
    raise OSError("disk full")


def test_write_succeeds_when_the_old_fixed_temp_name_is_taken(tmp_path: Path) -> None:
    (tmp_path / "status.json.tmp").mkdir()
    write_status(tmp_path, _status("ext-a"))
    assert read_status(tmp_path)["job_id"] == "ext-a"


def test_failed_write_leaves_the_target_untouched_and_no_temp_file(tmp_path: Path, monkeypatch) -> None:
    write_status(tmp_path, _status("ext-before"))
    before = (tmp_path / "status.json").read_text(encoding="utf-8")
    monkeypatch.setattr(run_artifacts, "dump_json_and_replace", _failing_dump)
    with pytest.raises(OSError):
        write_status(tmp_path, _status("ext-after"))
    assert (tmp_path / "status.json").read_text(encoding="utf-8") == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["status.json"]


def test_on_disk_format_is_indented_json_without_trailing_newline(tmp_path: Path) -> None:
    write_status(tmp_path, _status("ext-fmt"))
    text = (tmp_path / "status.json").read_text(encoding="utf-8")
    assert text == json.dumps(json.loads(text), indent=2)


def _alternate(
    job_id: str, my_turn: threading.Event, their_turn: threading.Event, run_dir: Path, failures: list[str],
) -> None:
    try:
        for _ in range(_WRITES_PER_WRITER):
            if not my_turn.wait(timeout=10):
                failures.append(f"{job_id}: turn never came")
                return
            my_turn.clear()
            write_status(run_dir, _status(job_id))
            their_turn.set()
    except Exception as exc:  # recorded for the main thread, which asserts the list is empty
        failures.append(f"{job_id}: {exc!r}")
        their_turn.set()
        raise


def _read_until(run_dir: Path, stop: threading.Event, parsed: list[str], errors: list[str]) -> None:
    path = run_dir / "status.json"
    while not stop.is_set():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            parsed.append(json.loads(text)["job_id"])
        except (json.JSONDecodeError, KeyError) as exc:
            errors.append(f"{exc}: {text!r}")


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="os.replace onto a path another handle holds open fails on Windows; "
    "the atomic write is exercised by the single-writer tests there",
)
def test_concurrent_writers_never_expose_a_truncated_file(tmp_path: Path) -> None:
    """A reader polling status.json never sees a partial file while two writers take turns.

    The writers alternate through an Event handoff, so their writes are
    serialised (as the in-process write lock would make them anyway). The
    test proves reader/writer atomicity, not overlapping writes.
    """
    write_status(tmp_path, _status("ext-seed"))
    a_turn, b_turn, stop = threading.Event(), threading.Event(), threading.Event()
    parsed: list[str] = []
    errors: list[str] = []
    failures: list[str] = []
    reader = threading.Thread(target=_read_until, args=(tmp_path, stop, parsed, errors))
    writers = [
        threading.Thread(target=_alternate, args=("ext-a", a_turn, b_turn, tmp_path, failures)),
        threading.Thread(target=_alternate, args=("ext-b", b_turn, a_turn, tmp_path, failures)),
    ]
    reader.start()
    for w in writers:
        w.start()
    a_turn.set()
    for w in writers:
        w.join(timeout=30)
    stop.set()
    reader.join(timeout=30)
    assert failures == []
    assert all(not w.is_alive() for w in writers)
    assert not reader.is_alive()
    assert errors == []
    assert parsed
    assert read_status(tmp_path)["job_id"] == "ext-b"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["status.json"]
