"""Incremental analysis — detect changes, classify files, carry forward findings."""
from __future__ import annotations

import json as _json
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


def _file_imports_changed(content: str, compiled: list, changed_stems: dict[str, str]) -> bool:
    """Return True if *content* imports any module whose stem is in *changed_stems*."""
    for line in content.splitlines():
        for pattern in compiled:
            m = pattern.search(line)
            if m:
                module_name = m.group(1).rsplit(".", 1)[-1].rsplit("/", 1)[-1]
                if module_name in changed_stems:
                    return True
                break
    return False


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
        if _file_imports_changed(content, compiled, changed_stems):
            dependents.add(f)
    return dependents


def carry_forward_findings(prev_jsonl: Path, output_jsonl: Path, unchanged_files: set[str]) -> int:
    """Copy findings for unchanged files from previous JSONL to output. Returns count."""
    if not prev_jsonl.exists():
        return 0
    count = 0
    try:
        output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with open(prev_jsonl) as inp, open(output_jsonl, "a") as out:
            for line in inp:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                if entry.get("file") in unchanged_files:
                    out.write(_json.dumps(entry) + "\n")
                    count += 1
    except OSError:
        return 0
    return count


@dataclass
class FileClassification:
    """Classified files for incremental analysis."""
    to_analyze: list[str] = field(default_factory=list)
    unchanged: set[str] = field(default_factory=set)
    full_reanalysis: bool = False


@dataclass
class ClassificationInput:
    """Grouped inputs for file classification."""
    src: Path
    files: list[str]
    prev_fingerprint: dict | None
    standards_dir: Path | None
    dimension: str
    language: str


def classify_files(src: Path | None = None, files: list[str] | None = None,
                   prev_fingerprint: dict | None = None,
                   standards_dir: Path | None = None, dimension: str = "",
                   language: str = "", *,
                   inputs: "ClassificationInput | None" = None) -> FileClassification:
    """Classify files into to_analyze (changed + dependents) and unchanged."""
    if inputs is not None:
        src = src or inputs.src
        files = files if files is not None else inputs.files
        prev_fingerprint = prev_fingerprint if prev_fingerprint is not None else inputs.prev_fingerprint
        standards_dir = standards_dir or inputs.standards_dir
        dimension = dimension or inputs.dimension
        language = language or inputs.language
    detection = detect_changed_files(src, files, prev_fingerprint, standards_dir, dimension)
    if detection.full_reanalysis:
        return FileClassification(to_analyze=list(files), full_reanalysis=True)
    dependents = find_dependents(detection.changed, files, src, language)
    to_analyze = detection.changed | dependents
    unchanged = set(files) - to_analyze
    return FileClassification(to_analyze=sorted(to_analyze), unchanged=unchanged)


def identify_backfill_files(
    all_files: list[str],
    prev_analyzed: list[str],
    already_queued: set[str],
) -> list[str]:
    """Identify files never analyzed that aren't already queued for this run.

    Returns files in the same order as all_files (preserving priority ordering).
    """
    covered = set(prev_analyzed) | already_queued
    return [f for f in all_files if f not in covered]
