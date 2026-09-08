"""Unit tests for tools/_ratchet.py's shared plumbing."""
from __future__ import annotations

import _ratchet


def test_iter_python_files_skips_excluded_dirs(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text("pass\n", encoding="utf-8")
    node_modules = pkg / "node_modules"
    node_modules.mkdir()
    (node_modules / "b.py").write_text("pass\n", encoding="utf-8")

    found = list(_ratchet.iter_python_files(tmp_path))

    assert found == [pkg / "a.py"]
