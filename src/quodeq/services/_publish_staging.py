"""Staging logic for publishing a project into the shared results repo.

Split out of shared_publish.py (Task 12): pure file-copy/merge operations
plus stage_project's one exception, a `git config user.name` read (see
audit finding C1). Invariants (spec):
- only completed runs (state == "done") are published
- explicit allowlist of source-of-truth files, never derived artifacts
- actions.jsonl is union-merged with the remote copy, never overwritten

`run_git` here is imported directly (not looked up on the shared_publish
facade): none of the shared_publish tests intercept the `config user.name`
read this module makes, so a top-level import is safe. Contrast with
_publish_git.py, whose push/commit run_git calls tests DO monkeypatch via
`shared_publish.run_git`.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from quodeq.services._wiring import (
    ACTIONS_LOG_FILENAME,
    DIMENSIONS_FILENAME,
    PUBLISHED_META_FILENAME,
    STATUS_FILENAME,
    UnsupportedSchemaError,
    copy_file_if_exists,
    copy_matching_files,
    ensure_dir,
    read_status,
    replace_json_file,
    run_git,
)

_RUN_FILES = (STATUS_FILENAME, DIMENSIONS_FILENAME, "events.jsonl")
_EVIDENCE_DIR = "evidence"
_EVALUATION_DIR = "evaluation"
_SCAN_FILENAME = "scan.json"


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
    ensure_dir(dest_run_dir)
    for name in _RUN_FILES:
        copy_file_if_exists(run_dir / name, dest_run_dir / name)
    evidence = run_dir / _EVIDENCE_DIR
    if evidence.is_dir():
        dest_evidence = dest_run_dir / _EVIDENCE_DIR
        ensure_dir(dest_evidence)
        copy_file_if_exists(evidence / "manifest.json", dest_evidence / "manifest.json")
        copy_matching_files(evidence, dest_evidence, "*_evidence.jsonl")
    evaluation = run_dir / _EVALUATION_DIR
    if evaluation.is_dir():
        # Frozen eval-time per-dimension scores (e.g. security.json) are the
        # source of truth read_run_data() needs to render a dashboard at
        # all -- without them a published clone renders an EMPTY dashboard.
        # Pattern-bounded like the evidence glob above: only .json files,
        # nothing else (markdown companions, stray files) from that dir.
        copy_matching_files(evaluation, dest_run_dir / _EVALUATION_DIR, "*.json")


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


def _publish_attribution(clone_root: Path) -> str:
    """Who is publishing, per `git config user.name` in the shared clone.

    Reads git config rather than GIT_AUTHOR_NAME/GIT_COMMITTER_NAME: those
    env vars only affect a new commit's recorded author/committer identity,
    not `git config` lookups. Falls back to "unknown" (never raises) so a
    missing git identity never blocks a publish -- audit finding C1 is about
    truthful attribution when it IS known, not about requiring one.
    """
    ok, out = run_git(["config", "user.name"], cwd=clone_root)
    author = out.strip() if ok else ""
    return author or "unknown"


def stage_project(project_dir: Path, dest_project_dir: Path) -> int:
    ensure_dir(dest_project_dir)
    copy_file_if_exists(
        project_dir / "repository_info.json",
        dest_project_dir / "repository_info.json",
    )
    # Project-level scan.json (quick-scan coverage metadata: total_files etc.)
    # is consumed by _fs_reports._enrich_with_coverage and the project-card
    # coverage reader -- without it, a published clone's dashboard/card never
    # shows a coverage header. Copied only when present; a project scanned
    # before this field existed simply stays absent on the clone too.
    copy_file_if_exists(project_dir / _SCAN_FILENAME, dest_project_dir / _SCAN_FILENAME)
    merge_actions_log(
        project_dir / ACTIONS_LOG_FILENAME,
        dest_project_dir / ACTIONS_LOG_FILENAME,
        dest_project_dir / ACTIONS_LOG_FILENAME,
    )
    runs = list_completed_runs(project_dir)
    for run_dir in runs:
        copy_run(run_dir, dest_project_dir / run_dir.name)

    # Record who published and when at publish time (audit finding C1),
    # rather than relying solely on git-log against the shared clone, which
    # published_meta() still falls back to for dirs published before this
    # file existed. dest_project_dir is <clone>/evaluations/<project_id>, so
    # its grandparent is the clone root -- the same root publish_project's
    # own `repo` variable points at.
    clone_root = dest_project_dir.parent.parent
    meta = {
        "publishedBy": _publish_attribution(clone_root),
        "publishedAt": int(time.time()),
    }
    replace_json_file(dest_project_dir / PUBLISHED_META_FILENAME, meta)

    return len(runs)
