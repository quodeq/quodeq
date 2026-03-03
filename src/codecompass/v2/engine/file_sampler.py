from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from codecompass.v2.engine.finding import Finding

_SKIP_DIRS = {".venv", "node_modules", "tests", ".git", ".worktrees", "__pycache__", ".tox", "dist", "build"}

_HIGH_RISK_NAMES = {
    "config", "auth", "main", "app", "server", "api", "db",
    "handler", "middleware", "route", "settings", "database",
    "login", "password", "secret", "admin", "security",
}

_ENTRY_POINT_MARKERS = [
    'if __name__',
    'app = Flask',
    'app = FastAPI',
    'urlpatterns',
    'createApp',
    'express()',
    'http.createServer',
    'public static void main',
]


@dataclass
class SampledFile:
    path: str
    content: str
    lines: int
    reason: str  # "detector_finding" | "high_risk_name" | "entry_point" | "large_file" | "random"
    truncated: bool


def sample_files(
    src: Path,
    findings: list[Finding],
    extensions: set[str],
    max_files: int = 20,
    max_lines: int = 500,
) -> list[SampledFile]:
    """Select files for LLM code review using a priority system."""
    candidates = _collect_candidates(src, extensions)
    if not candidates:
        return []

    finding_files = {f.file for f in findings if f.file}
    # Normalize finding paths to be relative to src
    finding_rel = set()
    for fp in finding_files:
        p = Path(fp)
        try:
            finding_rel.add(str(p.relative_to(src)))
        except ValueError:
            finding_rel.add(fp)

    selected_paths: list[str] = []
    selected_set: set[str] = set()

    def _add(path: str) -> bool:
        if path not in selected_set and len(selected_paths) < max_files:
            selected_set.add(path)
            selected_paths.append(path)
            return True
        return False

    # Categorize candidates
    detector_files: list[str] = []
    high_risk_files: list[str] = []
    entry_point_files: list[str] = []
    large_files: list[tuple[int, str]] = []  # (line_count, path)
    rest: list[str] = []

    for rel_path, line_count in candidates:
        if rel_path in finding_rel:
            detector_files.append(rel_path)
        else:
            stem = Path(rel_path).stem.lower()
            if stem in _HIGH_RISK_NAMES:
                high_risk_files.append(rel_path)
            else:
                rest.append(rel_path)
            large_files.append((line_count, rel_path))

    # Sort large files by line count descending
    large_files.sort(reverse=True)

    # Check entry points from rest + high_risk (lazily, reading content)
    for rel_path in rest + high_risk_files:
        if rel_path in selected_set:
            continue
        try:
            text = (src / rel_path).read_text(errors="replace")
            if any(marker in text for marker in _ENTRY_POINT_MARKERS):
                entry_point_files.append(rel_path)
        except OSError:
            continue

    # Priority 1: files with detector findings
    for p in detector_files:
        _add(p)

    # Priority 2: high-risk names
    for p in high_risk_files:
        _add(p)

    # Priority 3: entry points
    for p in entry_point_files:
        _add(p)

    # Priority 4: large files
    for _, p in large_files:
        _add(p)

    # Priority 5: random sample to fill remaining
    remaining = [p for p in rest if p not in selected_set]
    random.shuffle(remaining)
    for p in remaining:
        _add(p)

    # Now read content and build SampledFile objects
    result: list[SampledFile] = []
    for rel_path in selected_paths:
        reason = _classify(rel_path, finding_rel, entry_point_files)
        sf = _read_file(src, rel_path, reason, max_lines)
        if sf:
            result.append(sf)

    return result


def _collect_candidates(src: Path, extensions: set[str]) -> list[tuple[str, int]]:
    """Walk src and return (relative_path, line_count) for matching files."""
    candidates: list[tuple[str, int]] = []
    for p in src.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in extensions:
            continue
        # Skip excluded directories
        parts = p.relative_to(src).parts
        if any(part in _SKIP_DIRS for part in parts):
            continue
        try:
            line_count = p.read_text(errors="replace").count("\n")
        except OSError:
            continue
        candidates.append((str(p.relative_to(src)), line_count))
    return candidates


def _classify(rel_path: str, finding_rel: set[str], entry_points: list[str]) -> str:
    if rel_path in finding_rel:
        return "detector_finding"
    stem = Path(rel_path).stem.lower()
    if stem in _HIGH_RISK_NAMES:
        return "high_risk_name"
    if rel_path in entry_points:
        return "entry_point"
    return "random"


def _read_file(src: Path, rel_path: str, reason: str, max_lines: int) -> SampledFile | None:
    try:
        full = (src / rel_path).read_text(errors="replace")
    except OSError:
        return None
    all_lines = full.splitlines()
    total = len(all_lines)
    truncated = total > max_lines
    if truncated:
        content = "\n".join(all_lines[:max_lines]) + f"\n\n... (truncated, {total - max_lines} more lines)"
    else:
        content = full
    return SampledFile(
        path=rel_path,
        content=content,
        lines=total,
        reason=reason,
        truncated=truncated,
    )
