"""Standards file writing, read-instruction helpers, and multi-dimension rendering."""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis.prompts._context import NO_STANDARDS, NO_STANDARDS_FOR_DIM
from quodeq.analysis.prompts._renderers import render_compact_standards

_STANDARDS_FILE_PREFIX = ".quodeq_standards_"


def write_standards_file(work_dir: Path, dimension: str, content: str) -> Path:
    """Write standards checklist to a file in the work directory.

    Returns the absolute path to the written file.
    """
    standards_path = work_dir / f"{_STANDARDS_FILE_PREFIX}{dimension}.md"
    try:
        standards_path.write_text(content)
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


def render_all_standards(
    standards_dir: Path, dimensions: list[str], evaluators_dir: Path | None = None,
) -> str:
    """Render compact standards for all dimensions, separated by headers.

    Args:
        standards_dir: Root standards directory containing a ``compiled/`` subdirectory.
        dimensions: Dimension IDs to include (e.g. ``["security", "reliability"]``).
        evaluators_dir: Optional path to custom evaluator JSON files.

    Returns:
        Markdown string with per-dimension sections, or a fallback message
        when no standards are available.
    """
    compiled_dir = standards_dir / "compiled"
    _eval_dir = evaluators_dir
    if not compiled_dir.exists() and not (_eval_dir and _eval_dir.is_dir()):
        return NO_STANDARDS
    sections = []
    for dim in dimensions:
        compact = render_compact_standards(compiled_dir, dim, evaluators_dir=_eval_dir)
        if compact != NO_STANDARDS_FOR_DIM:
            sections.append(f"## {dim.title()}\n\n{compact}")
    return "\n\n".join(sections) if sections else NO_STANDARDS
