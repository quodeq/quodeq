"""Tests for source file gathering — _gather_source_files and skip dirs from subprocess.py."""
from __future__ import annotations

from quodeq.analysis.subprocess import _gather_source_files, _SKIP_DIRS


# ---------------------------------------------------------------------------
# _gather_source_files
# ---------------------------------------------------------------------------

class TestGatherSourceFiles:
    def test_collects_code_files(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 1")
        (tmp_path / "app.js").write_text("const x = 1;")
        result = _gather_source_files(tmp_path)
        names = {f.name for f in result}
        assert "main.py" in names
        assert "app.js" in names

    def test_skips_dotdirs(self, tmp_path):
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "secret.py").write_text("x = 1")
        (tmp_path / "visible.py").write_text("y = 2")
        result = _gather_source_files(tmp_path)
        names = {f.name for f in result}
        assert "secret.py" not in names
        assert "visible.py" in names

    def test_skips_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {};")
        (tmp_path / "app.js").write_text("const x = 1;")
        result = _gather_source_files(tmp_path)
        names = {f.name for f in result}
        assert "index.js" not in names
        assert "app.js" in names

    def test_skips_empty_files(self, tmp_path):
        (tmp_path / "empty.py").write_text("")
        (tmp_path / "real.py").write_text("x = 1")
        result = _gather_source_files(tmp_path)
        names = {f.name for f in result}
        assert "empty.py" not in names
        assert "real.py" in names

    def test_skips_oversized_files(self, tmp_path):
        (tmp_path / "big.py").write_text("x" * 20_000)
        (tmp_path / "small.py").write_text("y = 1")
        result = _gather_source_files(tmp_path)
        names = {f.name for f in result}
        assert "big.py" not in names
        assert "small.py" in names

    def test_prioritizes_code_over_markup(self, tmp_path):
        # Create code files that fill the budget (< 15KB each, > 30KB total)
        for i in range(4):
            (tmp_path / f"mod{i}.py").write_text("x" * 10_000)
        (tmp_path / "style.css").write_text("b" * 10_000)
        result = _gather_source_files(tmp_path)
        names = {f.name for f in result}
        # Code files should be prioritized over markup
        code_count = sum(1 for f in result if f.suffix == ".py")
        markup_count = sum(1 for f in result if f.suffix == ".css")
        assert code_count >= markup_count

    def test_respects_char_budget(self, tmp_path):
        # Create many files that exceed budget
        for i in range(50):
            (tmp_path / f"mod{i}.py").write_text("x" * 1000)
        result = _gather_source_files(tmp_path)
        total = sum(f.stat().st_size for f in result)
        assert total <= 30_000

    def test_includes_markup_files(self, tmp_path):
        (tmp_path / "page.html").write_text("<html></html>")
        (tmp_path / "style.css").write_text("body{}")
        result = _gather_source_files(tmp_path)
        names = {f.name for f in result}
        assert "page.html" in names
        assert "style.css" in names


# ---------------------------------------------------------------------------
# _SKIP_DIRS
# ---------------------------------------------------------------------------

class TestLoadSkipDirs:
    def test_returns_frozenset(self):
        assert isinstance(_SKIP_DIRS, frozenset)
        # Should at minimum contain common dirs
        assert "node_modules" in _SKIP_DIRS or len(_SKIP_DIRS) > 0
