"""Hardening regression tests for the file rate-limit store (crit #94)."""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from quodeq.api._rate_limit_file_store import FileRateLimitStore
from quodeq.api._rate_limit_factory import _validated_rate_limit_path, _DEFAULT_RATE_LIMIT_FILE

_skip_no_symlink = pytest.mark.skipif(
    sys.platform == "win32", reason="symlink/POSIX-mode semantics differ on Windows"
)


@_skip_no_symlink
def test_save_does_not_follow_symlink(tmp_path: Path):
    sentinel = tmp_path / "victim.txt"
    sentinel.write_text("DO NOT TRUNCATE", encoding="utf-8")
    target = tmp_path / "quodeq_rate_limits.json"
    os.symlink(sentinel, target)  # attacker plants a symlink at the predictable name

    store = FileRateLimitStore(path=target)
    store.record("1.2.3.4", 1000.0)

    # The victim file the symlink pointed at is untouched ...
    assert sentinel.read_text(encoding="utf-8") == "DO NOT TRUNCATE"
    # ... and the target is now a real file holding our JSON, not a link.
    assert not target.is_symlink()
    assert "1.2.3.4" in json.loads(target.read_text(encoding="utf-8"))


@_skip_no_symlink
def test_save_writes_0600_permissions(tmp_path: Path):
    target = tmp_path / "rl.json"
    FileRateLimitStore(path=target).record("1.2.3.4", 1000.0)
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600


@_skip_no_symlink
def test_validated_path_rejects_symlink(tmp_path: Path):
    real = tmp_path / "real.json"
    real.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    os.symlink(real, link)
    assert _validated_rate_limit_path(str(link)) == _DEFAULT_RATE_LIMIT_FILE
