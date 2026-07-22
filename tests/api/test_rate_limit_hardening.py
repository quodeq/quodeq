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


# ---------------------------------------------------------------------------
# #81 -- dead path-traversal validation: ".." check ran on resolved path
# ---------------------------------------------------------------------------

def test_validated_path_rejects_dotdot_in_raw_path(tmp_path: Path):
    """A path containing '..' must fall back to default even if it resolves cleanly.

    Before the fix, ``".." in resolved.parts`` ran on the already-resolved path
    (where ``..`` has already been collapsed by ``Path.resolve()``), so inputs
    like ``/tmp/foo/../bar`` were incorrectly accepted.
    """
    # Build a path that contains ".." lexically but resolves to a real location.
    # /tmp/foo/../bar resolves to /tmp/bar, so resolved.parts has no "..".
    # The pre-fix code accepts this; the fixed code must reject it.
    raw = str(tmp_path / "subdir" / ".." / "rate_limits.json")
    assert ".." in Path(raw).parts, "precondition: '..' must be in raw parts"
    assert ".." not in Path(raw).resolve().parts, "precondition: resolve() removes '..'"
    assert _validated_rate_limit_path(raw) == _DEFAULT_RATE_LIMIT_FILE


# ---------------------------------------------------------------------------
# REL-082/083 -- window/max env values must be positive; zero, negative, or
# malformed values fall back to the defaults instead of disabling the limiter
# (window <= 0) or blocking every client (max <= 0).
# ---------------------------------------------------------------------------

from quodeq.api._rate_limit_config import (
    _DEFAULT_RATE_LIMIT_MAX,
    _DEFAULT_RATE_LIMIT_WINDOW,
    _rate_limit_max,
    _rate_limit_window,
)


@pytest.mark.parametrize("raw", ["0", "-5", "abc", ""])
def test_rate_limit_window_falls_back_on_invalid_env(raw):
    assert _rate_limit_window(env={"QUODEQ_RATE_LIMIT_WINDOW": raw}) == _DEFAULT_RATE_LIMIT_WINDOW


def test_rate_limit_window_accepts_valid_env():
    assert _rate_limit_window(env={"QUODEQ_RATE_LIMIT_WINDOW": "30"}) == 30


@pytest.mark.parametrize("raw", ["0", "-1", "many", ""])
def test_rate_limit_max_falls_back_on_invalid_env(raw):
    assert _rate_limit_max(env={"QUODEQ_RATE_LIMIT_MAX": raw}) == _DEFAULT_RATE_LIMIT_MAX


def test_rate_limit_max_accepts_valid_env():
    assert _rate_limit_max(env={"QUODEQ_RATE_LIMIT_MAX": "5"}) == 5


# ---------------------------------------------------------------------------
# REL-078 -- a valid-JSON-but-non-object state file must not crash
# record()/check(); it is treated as empty state.
# ---------------------------------------------------------------------------

def test_load_treats_non_dict_json_as_empty(tmp_path: Path):
    target = tmp_path / "rl.json"
    target.write_text("[1, 2, 3]", encoding="utf-8")
    store = FileRateLimitStore(path=target)
    assert store.check("1.2.3.4", 1000.0) is False
    store.record("1.2.3.4", 1000.0)  # must not raise
    assert "1.2.3.4" in json.loads(target.read_text(encoding="utf-8"))


def test_load_treats_scalar_json_as_empty(tmp_path: Path):
    target = tmp_path / "rl.json"
    target.write_text('"corrupt"', encoding="utf-8")
    store = FileRateLimitStore(path=target)
    assert store.check("1.2.3.4", 1000.0) is False
