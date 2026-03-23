"""Evaluation fingerprinting — tracks what was analyzed and when."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


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


def _hash_file(path: Path) -> str | None:
    """SHA-256 hash of a file's content."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
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
