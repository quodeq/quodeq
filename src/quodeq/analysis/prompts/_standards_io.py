"""Standards file writing and read-instruction helpers."""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis.prompts.standards_file import standards_file_path


def write_standards_file(work_dir: Path, dimension: str, content: str) -> Path:
    """Write standards checklist to a file in the work directory.

    Returns the absolute path to the written file.
    """
    standards_path = standards_file_path(work_dir, dimension)
    try:
        standards_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise OSError(f"Failed to write standards file {standards_path}: {exc}") from exc
    return standards_path


def standards_read_instruction(standards_path: Path) -> str:
    """Return prompt text instructing the AI to read the standards file."""
    return (
        "**FIRST ACTION:** Load the standards checklist by calling the `get_standards` tool. "
        f"Only if you have no such tool, read it from `{standards_path}`.\n"
        "It contains all requirements you must evaluate against. "
        "Load it before analyzing any source files."
    )


def write_standards_and_instruction(work_dir: Path, dimension: str, content: str) -> str:
    """Write standards to a file and return the read instruction for the prompt."""
    standards_path = write_standards_file(work_dir, dimension, content)
    return standards_read_instruction(standards_path)

