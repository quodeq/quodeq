"""Where a run's standards checklist lives: next to its evidence.

The prompt builder writes it there; the findings server serves it back
through its ``get_standards`` tool, so the agent never reads outside the repo.
"""
from __future__ import annotations

from pathlib import Path

_STANDARDS_FILE_PREFIX = ".quodeq_standards_"


def standards_file_path(work_dir: Path, dimension: str) -> Path:
    """The checklist file for *dimension* in *work_dir* (the evidence dir)."""
    return work_dir / f"{_STANDARDS_FILE_PREFIX}{dimension}.md"
