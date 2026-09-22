"""Finding post-processing for the API runner: end_line inference, short-name
path resolution, and run-path derivation from the evidence file location.
"""
from __future__ import annotations

from pathlib import Path


def _infer_end_line(findings: list[dict]) -> None:
    """Derive end_line from snippet line count when the model omits it.

    Small local models often skip end_line, which collapses the dashboard
    highlight to a single line even when the model quoted several lines into
    snippet. If snippet has N>1 lines and end_line is unset, assume the span
    runs from line to line+N-1.
    """
    for f in findings:
        if f.get("end_line"):
            continue
        snippet = f.get("snippet") or ""
        line = f.get("line") or 0
        if line <= 0 or not snippet:
            continue
        n = snippet.count("\n") + 1
        if n > 1:
            f["end_line"] = line + n - 1


def _resolve_file_paths(findings: list[dict], source_paths: list[str]) -> list[dict]:
    """Resolve short filenames to full relative paths."""
    name_to_path: dict[str, str] = {}
    for p in source_paths:
        name = Path(p).name
        name_to_path[name] = p

    for f in findings:
        file_val = f.get("file", "")
        if file_val and "/" not in file_val and file_val in name_to_path:
            f["file"] = name_to_path[file_val]
    return findings


def _derive_run_paths(jsonl_file: Path) -> tuple[Path | None, Path | None]:
    """``(project_dir, run_dir)`` derived from the evidence file location.

    *jsonl_file* is ``<project_dir>/<run_id>/evidence/<dim>_evidence.jsonl``,
    so the project directory is its great-grandparent and the run directory
    its grandparent. Used by the context-enricher pipeline to load prior
    dismissals as precedents (fingerprints and, when the semantic-precedents
    flag is on, the embedded corpus).
    """
    project_dir = jsonl_file.parent.parent.parent if jsonl_file else None
    run_dir = jsonl_file.parent.parent if jsonl_file else None
    return project_dir, run_dir
