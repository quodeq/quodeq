"""Change detection — git-based and hash-based strategies."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from quodeq.analysis.fingerprint import (
    _RULES_BEARING_PROMPTS,
    _hash_file,
    _hash_prompts,
    _hash_prompts_map,
    _hash_standards,
)

_GIT_DIFF_TIMEOUT_S = 10


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
            cwd=str(src), capture_output=True, text=True, timeout=_GIT_DIFF_TIMEOUT_S,
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

    prev_prompts = prev_fingerprint.get("prompts_checksum")
    if prev_prompts is not None:
        # New format: per-file dict. Only rules-bearing prompts (those that
        # define what counts as a violation) trigger full re-analysis.
        # Framing or runner-specific instruction changes flow into the next
        # run's prompt naturally without invalidating prior carry-forward.
        if isinstance(prev_prompts, dict):
            current_prompts_map = _hash_prompts_map()
            for fname in _RULES_BEARING_PROMPTS:
                if prev_prompts.get(fname) != current_prompts_map.get(fname):
                    return ChangeDetectionResult(
                        full_reanalysis=True, reason=f"prompts changed ({fname})",
                    )
        else:
            # Legacy single-string format: any change to any prompt
            # triggers, matching pre-split behavior. Once this dim runs
            # again under the new code, its fingerprint upgrades to the
            # selective per-file format.
            current_prompts = _hash_prompts()
            if current_prompts != prev_prompts:
                return ChangeDetectionResult(
                    full_reanalysis=True, reason="prompts changed (legacy)",
                )

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

    # A previous fingerprint with file_hashes but no analyzed_files is either
    # legacy (pre-tracking) or a corrupt/incomplete write from a crashed run.
    # Either way it can't be trusted to mean "everything was analyzed", so
    # force a full re-analysis to heal the state on the next run.
    prev_analyzed = set(prev_fingerprint.get("analyzed_files", []))
    if prev_files and not prev_analyzed:
        return ChangeDetectionResult(
            full_reanalysis=True,
            reason="previous fingerprint has no analyzed_files (incomplete or pre-tracking)",
        )

    # Files that were fingerprinted but never analyzed (e.g. pool timed out)
    # must be treated as changed so they get picked up on the next run.
    not_analyzed = (file_set & prev_files) - prev_analyzed - changed
    changed |= not_analyzed

    return ChangeDetectionResult(changed=changed)
