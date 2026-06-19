"""Tests for check_imports.check_file — stderr warning on read error (#696)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# tools/ is not on sys.path by default; add it
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
import check_imports  # noqa: E402


class TestCheckFileWarning:
    def test_oserror_prints_warning_to_stderr(self, tmp_path: Path, capsys):
        """#696 — OSError reading a file must print a warning to stderr, not silently skip."""
        bad_path = tmp_path / "unreachable.py"
        bad_path.touch()

        with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
            result = check_imports.check_file(bad_path, "core")

        assert result == []
        captured = capsys.readouterr()
        assert "warning: skipping" in captured.err
        assert "unreachable.py" in captured.err
        assert "permission denied" in captured.err

    def test_unicode_error_prints_warning_to_stderr(self, tmp_path: Path, capsys):
        """#696 — UnicodeDecodeError reading a file must also produce a stderr warning."""
        bad_path = tmp_path / "binary.py"
        bad_path.touch()

        with patch.object(
            Path, "read_text", side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "bad byte")
        ):
            result = check_imports.check_file(bad_path, "core")

        assert result == []
        captured = capsys.readouterr()
        assert "warning: skipping" in captured.err
        assert "binary.py" in captured.err

    def test_clean_file_produces_no_warning(self, tmp_path: Path, capsys):
        """Readable files with no violations must not produce any stderr output."""
        clean_path = tmp_path / "clean.py"
        clean_path.write_text("x = 1\n", encoding="utf-8")
        result = check_imports.check_file(clean_path, "core")
        captured = capsys.readouterr()
        assert captured.err == ""
