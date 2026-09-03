"""#N — Unix file lock must time out and log, matching the Windows branch."""
from __future__ import annotations

import logging
import sys

import pytest


@pytest.mark.skipif(sys.platform == "win32", reason="exercises the fcntl branch")
def test_unix_lock_times_out_on_contention(tmp_path, monkeypatch, caplog) -> None:
    import fcntl

    from quodeq.data import _file_lock

    monkeypatch.setattr(_file_lock, "_WIN_LOCK_TIMEOUT_S", 0.2, raising=False)
    # The Unix path reads its own timeout constant; patch the module-level
    # constant the implementation will use (see Step 3) directly:
    monkeypatch.setattr(_file_lock, "_UNIX_LOCK_TIMEOUT_S", 0.2, raising=False)

    path = tmp_path / "lock"
    path.write_text("")
    # Keep the file objects alive for the whole test: a bare `.fileno()`
    # on a temporary `open()` result lets CPython close the fd via GC
    # right after this line, so `flock` would then act on a stale fd.
    holder_file = path.open("r+b")
    holder_fd = holder_file.fileno()
    fcntl.flock(holder_fd, fcntl.LOCK_EX)  # held for the whole test

    contender_file = path.open("r+b")
    contender_fd = contender_file.fileno()
    with caplog.at_level(logging.WARNING):
        with pytest.raises(TimeoutError):
            _file_lock.lock_file(contender_fd)

    assert any("lock" in rec.message.lower() for rec in caplog.records)
