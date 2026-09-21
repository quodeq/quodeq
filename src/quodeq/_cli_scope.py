"""--scope and single-file narrowing of the evaluation target.

Split from ``_cli_resolution.py`` to keep each module under 300 lines, and
re-exported from there (and, in turn, from ``cli_evaluation.py``) so the
historical import and patch paths keep working.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from quodeq.analysis.manifest import SourceManifest
from quodeq.analysis.manifest_models import AnalysisTarget


def _resolve_scope(src: Path, args: argparse.Namespace) -> tuple[str | None, bool]:
    """Resolve --scope flag against the source directory.

    Returns ``(scope_path, ok)`` where *ok* is False when validation fails
    (error already printed to stderr).
    """
    scope = getattr(args, "scope", None)
    if not scope or not src.is_dir():
        return None, True
    scoped = (src / scope).resolve()
    if not scoped.exists():
        print(f"Scope path does not exist: {scoped}", file=sys.stderr)
        return None, False
    if not scoped.is_relative_to(src):
        print(f"Scope must be within the repository: {scope}", file=sys.stderr)
        return None, False
    kind = "file" if scoped.is_file() else "folder"
    print(f"Scoped evaluation: {scope} ({kind}, repo root: {src})", file=sys.stderr)
    return scope, True


def _resolve_single_file(src: Path) -> tuple[Path, str | None]:
    """Detect single-file mode and return (project_root, relative_path | None)."""
    if not src.is_file():
        return src, None
    file_path = src
    project_root = file_path.parent
    candidate = file_path.parent
    while candidate != candidate.parent:
        if (candidate / ".git").exists():
            project_root = candidate
            break
        candidate = candidate.parent
    single_file = str(file_path.relative_to(project_root))
    print(f"Single-file evaluation: {single_file} (project root: {project_root})", file=sys.stderr)
    return project_root, single_file


def _override_manifest_single_file(language: str, single_file: str) -> SourceManifest:
    """Create a manifest covering exactly one source file."""
    ext = os.path.splitext(single_file)[1]
    language_stats = {ext: 1} if ext else {}
    target = AnalysisTarget(
        name=single_file, language=language,
        source_files=[single_file], total_files=1,
        language_stats=language_stats,
    )
    return SourceManifest(targets=[target], total_files=1, language_stats=language_stats)
