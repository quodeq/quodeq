"""Baseline keys are POSIX paths on every platform.

The baseline is committed from one OS and checked on three; a key built
with the native separator makes every entry both new and stale on Windows.
"""
from __future__ import annotations

from pathlib import PureWindowsPath

from tests.tools.test_no_refactor_narration import site_key

_LINE = 3


def test_site_key_is_posix_on_windows_paths() -> None:
    repo = PureWindowsPath(r"C:\repo")
    path = PureWindowsPath(r"C:\repo\tests\tools\a.py")
    assert site_key(path, repo, _LINE) == "tests/tools/a.py:3"
