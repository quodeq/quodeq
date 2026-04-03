"""Change detection — git-based and hash-based strategies."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from quodeq.analysis.fingerprint import _hash_file, _hash_standards


@dataclass
class ChangeDetectionResult:
    """Result of comparing current state against previous fingerprint."""
    changed: set[str] = field(default_factory=set)
    full_reanalysis: bool = False
    reason: str = ""


def _detect_via_git(src: Path, prev_commit: str) -> set[str] | None:
    """Try git diff for fast change detection. Returns None if unavailable."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{prev_commit}..HEAD"],
            cwd=str(src), capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return {f.strip() for f in result.stdout.splitlines() if f.strip()}
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _detect_via_hashes(src: Path, files: list[str], prev_hashes: dict[str, str]) -> set[str]:
    """Compare file hashes to detect changes."""
    changed = set()
    for f in files:
        current_hash = _hash_file(src / f)
        prev_hash = prev_hashes.get(f)
        if current_hash != prev_hash:
            changed.add(f)
    return changed


def detect_changed_files(
    src: Path, files: list[str], prev_fingerprint: dict | None,
    standards_dir: Path | None, dimension: str,
) -> ChangeDetectionResult:
    """Detect which files changed since the previous evaluation."""
    if prev_fingerprint is None:
        return ChangeDetectionResult(full_reanalysis=True, reason="no previous fingerprint")

    if standards_dir:
        current_std = _hash_standards(standards_dir, dimension)
        prev_std = prev_fingerprint.get("standards_checksum")
        if current_std != prev_std and prev_std is not None:
            return ChangeDetectionResult(full_reanalysis=True, reason="standards changed")

    prev_commit = prev_fingerprint.get("git_commit")
    file_set = set(files)
    git_changed = None
    if prev_commit:
        git_changed = _detect_via_git(src, prev_commit)

    if git_changed is not None:
        changed = git_changed & file_set
    else:
        prev_hashes = prev_fingerprint.get("file_hashes", {})
        changed = _detect_via_hashes(src, files, prev_hashes)

    prev_files = set(prev_fingerprint.get("file_hashes", {}).keys())
    new_files = file_set - prev_files
    changed |= new_files

    return ChangeDetectionResult(changed=changed)
