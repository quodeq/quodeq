"""dump_json_to_fd(fsync=): the bytes reach the disk before the descriptor is closed."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import quodeq.shared.json_state as json_state
from quodeq.shared.json_state import dump_json_to_fd


def _record_fsync(monkeypatch) -> list[int]:
    calls: list[int] = []
    real_fsync = os.fsync
    monkeypatch.setattr(json_state.os, "fsync", lambda fd: (calls.append(fd), real_fsync(fd))[1])
    return calls


def test_fsync_flushes_the_json_to_disk(tmp_path: Path, monkeypatch) -> None:
    calls = _record_fsync(monkeypatch)
    fd, name = tempfile.mkstemp(dir=tmp_path)
    dump_json_to_fd(fd, {"pending": ["a.py"]}, fsync=True)
    assert calls == [fd]
    assert Path(name).read_text(encoding="utf-8") == '{"pending": ["a.py"]}'


def test_no_fsync_by_default(tmp_path: Path, monkeypatch) -> None:
    calls = _record_fsync(monkeypatch)
    fd, name = tempfile.mkstemp(dir=tmp_path)
    dump_json_to_fd(fd, {"a": 1}, indent=2)
    assert calls == []
    assert Path(name).read_text(encoding="utf-8") == '{\n  "a": 1\n}'
