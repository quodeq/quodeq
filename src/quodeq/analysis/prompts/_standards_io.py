"""Standards file writing and read-instruction helpers."""
from __future__ import annotations

from pathlib import Path

_STANDARDS_FILE_PREFIX = ".quodeq_standards_"


def write_standards_file(work_dir: Path, dimension: str, content: str) -> Path:
    """Write standards checklist to a file in the work directory.

    Returns the absolute path to the written file.
    """
    standards_path = work_dir / f"{_STANDARDS_FILE_PREFIX}{dimension}.md"
    try:
        standards_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise OSError(f"Failed to write standards file {standards_path}: {exc}") from exc
    return standards_path


def standards_read_instruction(standards_path: Path) -> str:
    """Return prompt text instructing the AI to read the standards file."""
    return (
        f"**FIRST ACTION:** Read the standards checklist from `{standards_path}`\n"
        f"This file contains all requirements you must evaluate against. "
        f"Read it before analyzing any source files."
    )


def write_standards_and_instruction(work_dir: Path, dimension: str, content: str) -> str:
    """Write standards to a file and return the read instruction for the prompt."""
    standards_path = write_standards_file(work_dir, dimension, content)
    return standards_read_instruction(standards_path)

