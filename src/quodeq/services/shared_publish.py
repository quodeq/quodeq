"""Staging logic for publishing a project into the shared results repo.

Pure file operations, no git. Invariants (spec):
- only completed runs (state == "done") are published
- explicit allowlist of source-of-truth files, never derived artifacts
- actions.jsonl is union-merged with the remote copy, never overwritten
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from quodeq.data.actions_log import ACTIONS_LOG_FILENAME
from quodeq.shared.dimensions_state import FILENAME as DIMENSIONS_FILENAME
from quodeq.shared.run_status import STATUS_FILENAME, UnsupportedSchemaError, read_status

_RUN_FILES = (STATUS_FILENAME, DIMENSIONS_FILENAME, "events.jsonl")
_EVIDENCE_DIR = "evidence"


def list_completed_runs(project_dir: Path) -> list[Path]:
    runs: list[Path] = []
    for entry in sorted(project_dir.iterdir()):
        if not entry.is_dir():
            continue
        try:
            status = read_status(entry)
        except UnsupportedSchemaError:
            # Skip runs with unsupported schema versions
            continue
        if status and status.get("state") == "done":
            runs.append(entry)
    return runs


def copy_run(run_dir: Path, dest_run_dir: Path) -> None:
    dest_run_dir.mkdir(parents=True, exist_ok=True)
    for name in _RUN_FILES:
        src = run_dir / name
        if src.exists():
            shutil.copy2(src, dest_run_dir / name)
    evidence = run_dir / _EVIDENCE_DIR
    if evidence.is_dir():
        dest_evidence = dest_run_dir / _EVIDENCE_DIR
        dest_evidence.mkdir(exist_ok=True)
        manifest = evidence / "manifest.json"
        if manifest.exists():
            shutil.copy2(manifest, dest_evidence / "manifest.json")
        for src in sorted(evidence.glob("*_evidence.jsonl")):
            shutil.copy2(src, dest_evidence / src.name)


def _timestamp_key(line: str) -> tuple[int, str]:
    try:
        ts = json.loads(line).get("timestamp")
    except (json.JSONDecodeError, AttributeError, TypeError):
        return (1, "")
    if not ts:
        return (1, "")
    return (0, str(ts))


def merge_actions_log(ours: Path, theirs: Path, dest: Path) -> None:
    seen: set[str] = set()
    lines: list[str] = []
    for source in (ours, theirs):
        if not source.exists():
            continue
        for raw in source.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and line not in seen:
                seen.add(line)
                lines.append(line)
    if not lines:
        return
    lines.sort(key=_timestamp_key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def stage_project(project_dir: Path, dest_project_dir: Path) -> int:
    dest_project_dir.mkdir(parents=True, exist_ok=True)
    info = project_dir / "repository_info.json"
    if info.exists():
        shutil.copy2(info, dest_project_dir / "repository_info.json")
    merge_actions_log(
        project_dir / ACTIONS_LOG_FILENAME,
        dest_project_dir / ACTIONS_LOG_FILENAME,
        dest_project_dir / ACTIONS_LOG_FILENAME,
    )
    runs = list_completed_runs(project_dir)
    for run_dir in runs:
        copy_run(run_dir, dest_project_dir / run_dir.name)
    return len(runs)
