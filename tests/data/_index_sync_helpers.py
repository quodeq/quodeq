"""Run-directory seeding for tests/data/test_index_sync*.py siblings."""
from __future__ import annotations

from pathlib import Path


def _make_run_dir(root: Path, project: str, run_id: str) -> Path:
    d = root / project / run_id
    (d / "evidence").mkdir(parents=True)
    (d / "evidence" / "manifest.json").write_text("{}")
    return d
