"""Evaluation fingerprinting — tracks what was analyzed and when.

Uses subprocess to call ``git`` directly — fingerprinting needs the
commit hash and repo state, which are only available from git itself.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from quodeq.data.fs.report_parser.runs import list_runs


def _get_git_commit(src: Path) -> str | None:
    """Get current HEAD commit hash, or None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(src), capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


_HASH_CHUNK_SIZE = 1 << 16  # 64 KiB


def _hash_file(path: Path) -> str | None:
    """SHA-256 hash of a file's content, streamed in chunks to limit memory."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(_HASH_CHUNK_SIZE):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _hash_standards(standards_dir: Path, dimension: str) -> str | None:
    """SHA-256 of the compiled standards JSON for a dimension."""
    compiled = standards_dir / "compiled" / f"{dimension}.json"
    if not compiled.exists():
        return None
    try:
        return hashlib.sha256(compiled.read_bytes()).hexdigest()
    except OSError:
        return None


def build_fingerprint(src: Path, files: list[str], dimension: str, standards_dir: Path | None, *, analyzed_files: set[str] | None = None) -> dict:
    """Build a fingerprint for the current evaluation state."""
    file_hashes = {}
    for f in files:
        h = _hash_file(src / f)
        if h:
            file_hashes[f] = h
    return {
        "dimension": dimension,
        "git_commit": _get_git_commit(src),
        "file_hashes": file_hashes,
        "standards_checksum": _hash_standards(standards_dir, dimension) if standards_dir else None,
        "analyzed_files": sorted(analyzed_files) if analyzed_files else [],
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def save_fingerprint(fingerprint: dict, evidence_dir: Path) -> Path:
    """Save fingerprint to the evidence directory."""
    dim = fingerprint["dimension"]
    path = evidence_dir / f"{dim}_fingerprint.json"
    path.write_text(json.dumps(fingerprint, indent=2))
    return path


def load_fingerprint(evidence_dir: Path, dimension: str) -> dict | None:
    """Load a fingerprint, or None if not found."""
    path = evidence_dir / f"{dimension}_fingerprint.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def find_previous_fingerprint(
    evidence_dir: Path, dimension: str,
) -> tuple[dict | None, Path | None]:
    """Find the fingerprint and evidence dir from the most recent previous run.

    Walks the run history to find the latest run (other than the current one)
    that has a fingerprint for the given dimension.
    """
    from quodeq.analysis.subagents.verify import resolve_evidence_paths

    paths_info = resolve_evidence_paths(evidence_dir)
    if not paths_info:
        return None, None

    current_run_id, project_uuid, reports_base = paths_info
    for run_info in list_runs(reports_base, project_uuid):
        if run_info.run_id == current_run_id:
            continue
        run_dir = reports_base / project_uuid / run_info.run_id
        # Only carry forward from runs that completed (have a scored report)
        eval_report = run_dir / "evaluation" / f"{dimension}.json"
        if not eval_report.is_file():
            continue
        prev_evidence = run_dir / "evidence"
        fp = load_fingerprint(prev_evidence, dimension)
        if fp:
            return fp, prev_evidence
    return None, None
