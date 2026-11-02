"""Every runtime data file in the package must be bundled by both desktop specs.

PyInstaller only ships .py modules on its own; anything read from disk next to
the code (JSON schemas, the /logs viewer page) needs a ``datas`` entry. The
Windows and macOS specs each keep their own list, and api/pages/ was missing
from both for several releases: create_app crashed at startup and the packaged
API never served.
"""
from __future__ import annotations

from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_PKG = _REPO / "src" / "quodeq"
_SPECS = [
    _REPO / "packaging" / "windows" / "quodeq_dashboard.spec",
    _REPO / "packaging" / "macos" / "quodeq_dashboard.spec",
]
# Trees bundled whole, the frontend source, and files nothing reads at runtime.
_SKIP_TOP = {"data", "static", "ui"}
_SKIP_SUFFIXES = {".py", ".pyc", ".md", ".typed"}


def _runtime_data_dirs() -> set[str]:
    dirs = set()
    for path in _PKG.rglob("*"):
        rel = path.relative_to(_PKG)
        if not path.is_file() or rel.parts[0] in _SKIP_TOP or "__pycache__" in rel.parts:
            continue
        if path.suffix in _SKIP_SUFFIXES:
            continue
        dirs.add("/".join(("quodeq",) + rel.parent.parts))
    return dirs


@pytest.mark.parametrize("spec", _SPECS, ids=lambda p: p.parent.name)
def test_spec_bundles_every_runtime_data_dir(spec: Path) -> None:
    text = spec.read_text(encoding="utf-8")
    missing = sorted(d for d in _runtime_data_dirs() if f'"{d}"' not in text)
    assert not missing, f"{spec.relative_to(_REPO)} has no datas entry for {missing}"
