"""not_a_directory_reason names which mistake a non-directory path is."""
from __future__ import annotations

from pathlib import Path

from quodeq.shared.paths import not_a_directory_reason


def test_a_file_is_named_as_a_file(tmp_path: Path) -> None:
    target = tmp_path / "player.js"
    target.write_text("x", encoding="utf-8")
    assert not_a_directory_reason(target) == "points at a file, not a directory"


def test_a_missing_path_is_named_as_missing(tmp_path: Path) -> None:
    assert not_a_directory_reason(tmp_path / "gone") == "does not exist"
