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

from quodeq.analysis.subagents.verify import resolve_evidence_paths
from quodeq.config.paths import default_paths
from quodeq.data.fs.report_parser.runs import list_runs
from quodeq.shared.validation import validate_path_segment

_GIT_TIMEOUT_S = 5


def _get_git_commit(src: Path) -> str | None:
    """Get current HEAD commit hash, or None if not a git repo.

    This is the single git abstraction point for fingerprinting: all git
    subprocess access is funnelled through this helper, making it easy to
    mock or replace in tests.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(src), capture_output=True, text=True, timeout=_GIT_TIMEOUT_S,
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
    """SHA-256 of the compiled standards JSON for a dimension.

    Uses the same chunked hashing approach as ``_hash_file`` to avoid
    reading the entire file into memory at once.
    """
    compiled = standards_dir / "compiled" / f"{dimension}.json"
    if not compiled.exists():
        return None
    return _hash_file(compiled)


def _hash_prompts(prompts_dir: Path | None = None) -> str | None:
    """SHA-256 over the concatenated *.md prompt files in *prompts_dir*.

    A change to any prompt template (notably ``evaluation_rules.md``) shifts
    LLM behavior even when source files and standards are byte-identical.
    Mixing the prompt directory's content into the fingerprint forces
    re-analysis after a prompt update — otherwise carry-forward keeps
    serving findings produced under the old rules.
    """
    if prompts_dir is None:
        prompts_dir = default_paths().prompts_dir
    if prompts_dir is None or not prompts_dir.is_dir():
        return None
    h = hashlib.sha256()
    for path in sorted(prompts_dir.glob("*.md")):
        per_file = _hash_file(path)
        if per_file is None:
            continue
        h.update(path.name.encode())
        h.update(per_file.encode())
    return h.hexdigest()


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
        "prompts_checksum": _hash_prompts(),
        "analyzed_files": sorted(analyzed_files) if analyzed_files else [],
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def save_fingerprint(fingerprint: dict, evidence_dir: Path) -> Path:
    """Save fingerprint to the evidence directory."""
    dim = fingerprint["dimension"]
    validate_path_segment(dim)
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


def _queue_taken_files(evidence_dir: Path, dimension: str) -> set[str]:
    """Read files that were dispatched to agents from a dim's queue.json.

    Returns the union of files appearing in any taken batch. Empty set if the
    queue is missing or unreadable. Used to salvage analyzed_files from runs
    that crashed or were cancelled before the fingerprint was finalized.
    """
    path = evidence_dir / f"{dimension}_queue.json"
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return set()
    taken = data.get("taken") if isinstance(data, dict) else None
    if not isinstance(taken, list):
        return set()
    out: set[str] = set()
    for entry in taken:
        files = entry.get("files") if isinstance(entry, dict) else None
        if isinstance(files, list):
            out.update(f for f in files if isinstance(f, str))
    return out


def find_previous_fingerprint(
    evidence_dir: Path, dimension: str,
) -> tuple[dict | None, Path | None]:
    """Find the fingerprint and evidence dir from the most recent previous run.

    Walks the run history to find the latest run (other than the current one)
    that has a fingerprint for the given dimension. Crash/cancel salvage:
    when the previous run died before finalising, its `analyzed_files` set
    is stale — we union in whatever files the queue actually dispatched so
    the catch-up loop doesn't keep re-sweeping work that already happened.
    """
    paths_info = resolve_evidence_paths(evidence_dir)
    if not paths_info:
        return None, None

    current_run_id, project_uuid, reports_base = paths_info
    for run_info in list_runs(reports_base, project_uuid):
        if run_info.run_id == current_run_id:
            continue
        run_dir = reports_base / project_uuid / run_info.run_id
        prev_evidence = run_dir / "evidence"
        fp = load_fingerprint(prev_evidence, dimension)
        if not fp:
            continue
        # Augment analyzed_files with anything the queue dispatched. For
        # cleanly finalised runs this is a no-op (queue.taken ⊆ analyzed_files
        # already). For crashed/cancelled runs it salvages partial work.
        queue_analyzed = _queue_taken_files(prev_evidence, dimension)
        if queue_analyzed:
            current_analyzed = set(fp.get("analyzed_files") or [])
            merged = current_analyzed | queue_analyzed
            if merged != current_analyzed:
                fp["analyzed_files"] = sorted(merged)
        return fp, prev_evidence
    return None, None
