"""build_manifest surfaces directories the walk could not list.

``WalkCounts.unreadable_dirs`` was already tallied by ``iter_source_files``,
but nothing in src read it: a permission-denied subtree was skipped in
total silence, so a partially-scanned repo looked identical to a
fully-scanned one. It now travels on ``SourceManifest`` the same way
``skipped_untracked`` does, and is logged once at warning when non-zero.
"""
from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

import pytest

from quodeq.analysis.manifest import build_manifest

from tests.analysis._manifest_fixtures import detection  # noqa: F401 -- pytest fixture

_LOGGER_NAME = "quodeq.analysis.manifest_build"
_NEEDLE = "could not be listed"


def _unreadable_log_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if _NEEDLE in r.getMessage()]


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="chmod-based permission denial is ineffective as root or on Windows",
)
def test_unreadable_subdir_is_reported_and_logged_at_warning(
    tmp_path: Path, detection: dict, caplog,
) -> None:
    for name in ("app0.py", "app1.py", "app2.py"):
        (tmp_path / name).write_text("x = 1\n", encoding="utf-8")
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "secret.py").write_text("y = 2\n", encoding="utf-8")
    locked.chmod(0)
    try:
        with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
            manifest = build_manifest(tmp_path, detection)
    finally:
        locked.chmod(stat.S_IRWXU)

    assert manifest.unreadable_dirs == 1
    lines = _unreadable_log_lines(caplog)
    assert len(lines) == 1
    assert "1 directory" in lines[0]


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="chmod-based permission denial is ineffective as root or on Windows",
)
def test_nothing_logged_when_every_dir_is_readable(
    tmp_path: Path, detection: dict, caplog,
) -> None:
    for name in ("app0.py", "app1.py", "app2.py"):
        (tmp_path / name).write_text("x = 1\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        manifest = build_manifest(tmp_path, detection)

    assert manifest.unreadable_dirs == 0
    assert _unreadable_log_lines(caplog) == []
