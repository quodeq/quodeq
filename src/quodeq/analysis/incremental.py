"""Incremental analysis — detect changes, classify files, carry forward findings."""
from __future__ import annotations

import re
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


def find_dependents(changed: set[str], files: list[str], src: Path, language: str) -> set[str]:
    """Find files that directly import any changed file (1 level deep)."""
    from quodeq.analysis.subagents.priority import load_priority_config

    config = load_priority_config()
    lang_key = language.lower()
    _LANG_ALIASES = {"typescript": "javascript", "jsx": "javascript", "tsx": "javascript", "kotlin": "java"}
    lang_key = _LANG_ALIASES.get(lang_key, lang_key)
    patterns = config.get("import_patterns", {}).get(lang_key)
    if not patterns:
        return set()

    changed_stems = {Path(f).stem: f for f in changed}
    compiled = [re.compile(p) for p in patterns]
    dependents: set[str] = set()

    for f in files:
        if f in changed:
            continue
        full_path = src / f
        if not full_path.exists():
            continue
        try:
            content = full_path.read_text(errors="ignore")
        except OSError:
            continue
        for line in content.splitlines():
            for pattern in compiled:
                m = pattern.search(line)
                if m:
                    imported = m.group(1)
                    module_name = imported.rsplit(".", 1)[-1].rsplit("/", 1)[-1]
                    if module_name in changed_stems:
                        dependents.add(f)
                    break
            if f in dependents:
                break
    return dependents
