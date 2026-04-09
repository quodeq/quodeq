"""Finding verification I/O — evidence path resolution and JSONL parsing."""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from quodeq.data.fs.report_parser.runs import list_runs
from quodeq.shared.logging import log_debug
from quodeq.shared.utils import open_text


def _find_previous_evidence(reports_root: Path, project_uuid: str, current_run_id: str, dim_id: str) -> Path | None:
    """Find the JSONL evidence file from the most recent previous run."""
    runs = list_runs(reports_root, project_uuid, limit=20)
    for run in runs:
        if run.run_id == current_run_id:
            continue
        run_dir = reports_root / project_uuid / run.run_id
        # Only use evidence from runs that completed (have a scored report)
        if not (run_dir / "evaluation" / f"{dim_id}.json").is_file():
            continue
        prev_jsonl = run_dir / "evidence" / f"{dim_id}_evidence.jsonl"
        if prev_jsonl.exists() and prev_jsonl.stat().st_size > 0:
            return prev_jsonl
    return None


def _parse_finding_line(line: str) -> dict | None:
    """Parse a single JSONL line into a finding dict, or None if invalid."""
    line = line.strip()
    if not line:
        return None
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        return None
    if entry.get("p") and entry.get("t") in ("violation", "compliance"):
        return entry
    return None


def _load_previous_findings(
    jsonl_path: Path,
    open_fn: Callable[[Path], Any] | None = None,
) -> list[dict]:
    """Load all findings from a JSONL file.

    *open_fn* is an injectable file opener (defaults to ``open_text``).
    """
    if not jsonl_path.exists():
        return []
    _open = open_fn or open_text
    try:
        findings: list[dict] = []
        with _open(jsonl_path) as f:
            for line in f:
                entry = _parse_finding_line(line)
                if entry is not None:
                    findings.append(entry)
        return findings
    except OSError as exc:
        log_debug(f"Cannot read findings JSONL {jsonl_path}: {exc}")
        return []


def resolve_evidence_paths(evidence_dir: Path) -> tuple[str, str, Path] | None:
    """Walk up from evidence_dir to find run_id, project_uuid, reports_base."""
    edir = Path(evidence_dir)
    while edir.name != "evidence" and edir != edir.parent:
        edir = edir.parent
    if edir.name != "evidence":
        return None
    run_dir = edir.parent
    return run_dir.name, run_dir.parent.name, run_dir.parent.parent


def _resolve_previous_evidence(
    evidence_dir: Path,
    dim_id: str,
    cache: dict[tuple[str, str], tuple[list[dict], int, int]] | None,
    cache_key: tuple[str, str],
) -> tuple[Path | None, bool]:
    """Resolve path to the previous evidence JSONL file.

    Returns (prev_jsonl_path, already_cached).  When *already_cached* is True
    the caller should use the cache hit instead.  A ``None`` path means no
    previous evidence exists.
    """
    paths = resolve_evidence_paths(evidence_dir)
    if paths is None:
        if cache is not None:
            cache[cache_key] = ([], 0, 0)
        return None, False
    current_run_id, project_uuid, reports_base = paths
    prev_jsonl = _find_previous_evidence(reports_base, project_uuid, current_run_id, dim_id)
    if prev_jsonl is None:
        if cache is not None:
            cache[cache_key] = ([], 0, 0)
        return None, False
    return prev_jsonl, False
