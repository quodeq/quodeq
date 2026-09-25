"""dump_json_and_replace(mode=): the published file gets the mode before it is visible."""
from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path

import pytest

from quodeq.shared.json_state import dump_json_and_replace

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")


def _loose_temp(directory: Path) -> tuple[int, str]:
    fd, name = tempfile.mkstemp(dir=directory)
    os.chmod(name, 0o644)
    return fd, name


def test_mode_is_applied_to_the_published_file(tmp_path: Path) -> None:
    fd, name = _loose_temp(tmp_path)
    target = tmp_path / "state.json"
    dump_json_and_replace(fd, name, target, {"a": [1.5]}, mode=0o600)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert target.read_text(encoding="utf-8") == '{"a": [1.5]}'


def test_without_mode_the_temp_file_mode_is_kept(tmp_path: Path) -> None:
    fd, name = _loose_temp(tmp_path)
    target = tmp_path / "state.json"
    dump_json_and_replace(fd, name, target, {})
    assert stat.S_IMODE(target.stat().st_mode) == 0o644
