"""Staging logic for publishing a project into the shared results repo.

Split out of shared_publish.py: pure file-copy/merge operations
plus stage_project's one exception, a `git config user.name` read.
Invariants (spec):
- only completed runs (state == "done") are published
- explicit allowlist of source-of-truth files, never derived artifacts
- no machine path of the publisher's: a local project's ``path`` is blanked
  and each report's ``project`` names only the folder (publish_scrub.py)
- actions.jsonl is union-merged with the remote copy, never overwritten
- a run keeps the form the shared repo has it in (full or archive); a new
  one takes its local form; the local archive is read, never restored
- stage_project reports every path it wrote, and publish stages only those

`run_git` here is imported directly (not looked up on the shared_publish
facade): none of the shared_publish tests intercept the `config user.name`
read this module makes, so a top-level import is safe. Contrast with
_publish_git.py, whose push/commit run_git calls tests DO monkeypatch via
`shared_publish.run_git`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from quodeq.core.run.state import RunState
from quodeq.services.publish_scrub import published_repository_info, scrub_report_paths
from quodeq.services.wiring import (
    ACTIONS_LOG_FILENAME,
    DIMENSIONS_FILENAME,
    PUBLISHED_META_FILENAME,
    STATUS_FILENAME,
    UnsupportedSchemaError,
    copy_file_if_exists,
    copy_matching_files, copy_reports_plain,
    ensure_dir,
    merge_action_log_files,
    read_repository_info,
    read_status,
    replace_json_file,
    run_git,
)
from quodeq.services.wiring_sync import (
    ARCHIVE_FILENAME,
    COLD_NAME,
    PRECEDENTS_NAME,
    SCALARS_NAME,
    is_cold,
    RunArchiveError,
    clone_run_contained,
    extract_members_to,
    is_archived,
    pack_run_logs,
    repack_without_db,
)
from quodeq.shared.constants import EVIDENCE_DIRNAME, MANIFEST_FILENAME

_RUN_FILES = (STATUS_FILENAME, DIMENSIONS_FILENAME)
EVENTS_FILENAME = "events.jsonl"
_EVIDENCE_PATTERN = "*_evidence.jsonl"
_EVALUATION_DIR = "evaluation"
_SCAN_FILENAME = "scan.json"
_REPO_INFO_FILENAME = "repository_info.json"


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
        if status and status.get("state") == RunState.DONE:
            runs.append(entry)
    return runs


def _copy(src: Path, dest: Path, written: list[Path]) -> None:
    if copy_file_if_exists(src, dest):
        written.append(dest)


def _copy_matching(src_dir: Path, dest_dir: Path, pattern: str, written: list[Path]) -> None:
    if src_dir.is_dir():
        written.extend(copy_matching_files(src_dir, dest_dir, pattern))


def _archive_form(run_dir: Path, dest_run_dir: Path) -> bool:
    """The form rule: a run keeps the form the shared repo has it in; a new one takes its local form.

    The archive wins over a log beside it: a clone that opened the run
    unpacked the log there, untracked.
    """
    if (dest_run_dir / ARCHIVE_FILENAME).is_file():
        return True
    if (dest_run_dir / EVENTS_FILENAME).is_file():
        return False
    return is_archived(run_dir)


def _copy_logs(run_dir: Path, dest_run_dir: Path, written: list[Path]) -> None:
    """The event log and evidence logs, in the run's published form, read from the local archive when archived."""
    archive = run_dir / ARCHIVE_FILENAME
    if is_cold(run_dir):  # no logs left: the frozen grades, dismissals and marker are what a clone can read
        for sidecar in (SCALARS_NAME, PRECEDENTS_NAME, COLD_NAME):
            _copy(run_dir / sidecar, dest_run_dir / sidecar, written)
        return
    if _archive_form(run_dir, dest_run_dir):
        if is_archived(run_dir):
            written.append(repack_without_db(archive, dest_run_dir / ARCHIVE_FILENAME))
        elif (run_dir / EVENTS_FILENAME).is_file():
            written.append(pack_run_logs(run_dir, dest_run_dir / ARCHIVE_FILENAME))
        for sidecar in (SCALARS_NAME, PRECEDENTS_NAME):
            _copy(run_dir / sidecar, dest_run_dir / sidecar, written)
    elif is_archived(run_dir):
        written.extend(extract_members_to(archive, dest_run_dir))
    else:
        evidence = run_dir / EVIDENCE_DIRNAME
        expected = (run_dir / EVENTS_FILENAME).is_file()
        expected_evidence = evidence.is_dir() and any(evidence.glob(_EVIDENCE_PATTERN))
        _copy(run_dir / EVENTS_FILENAME, dest_run_dir / EVENTS_FILENAME, written)
        if expected and dest_run_dir / EVENTS_FILENAME not in written:
            raise RunArchiveError(f"run {run_dir.name} changed while publishing, retry")
        before = len(written)
        _copy_matching(evidence, dest_run_dir / EVIDENCE_DIRNAME, _EVIDENCE_PATTERN, written)
        if expected_evidence and len(written) == before:
            raise RunArchiveError(f"run {run_dir.name} changed while publishing, retry")


def copy_run(run_dir: Path, dest_run_dir: Path) -> list[Path]:
    """Copy the run's published files into *dest_run_dir*; the paths written.

    Never restores, stamps or changes the local run. Raises ``RunArchiveError``
    (before any other file is written) when its archive is unsafe or unreadable.
    Never copies ``evaluation.db``, ``run.log`` or dot-files.
    """
    ensure_dir(dest_run_dir)
    written: list[Path] = []
    try:
        _copy_logs(run_dir, dest_run_dir, written)
    except FileNotFoundError as exc:  # archived or restored meanwhile: the file it was reading went
        raise RunArchiveError(f"run {run_dir.name} changed while publishing, retry") from exc
    for name in _RUN_FILES:
        _copy(run_dir / name, dest_run_dir / name, written)
    evidence = run_dir / EVIDENCE_DIRNAME
    if evidence.is_dir():
        dest_evidence = dest_run_dir / EVIDENCE_DIRNAME
        ensure_dir(dest_evidence)
        _copy(evidence / MANIFEST_FILENAME, dest_evidence / MANIFEST_FILENAME, written)
    # Frozen eval-time per-dimension scores (e.g. security.json) are the
    # source of truth read_run_data() needs to render a dashboard at all;
    # without them a published clone renders an EMPTY dashboard. Only the
    # reports, written plain whatever form the local run keeps them in.
    reports = copy_reports_plain(run_dir / _EVALUATION_DIR, dest_run_dir / _EVALUATION_DIR)
    scrub_report_paths(reports)
    written.extend(reports)
    return written


def merge_actions_log(ours: Path, theirs: Path, dest: Path) -> None:
    """Union-merge *ours* and *theirs* into *dest*, deduped and timestamp-sorted.

    Thin delegate to ``data.actions_log.merge_action_log_files``: a non-UTF8
    source raises ``ValueError`` here too, which ``stage_project``'s caller
    (``publish_project``) already catches and turns into ``PublishError``.
    """
    merge_action_log_files(dest, (ours, theirs))


def _publish_attribution(clone_root: Path) -> str:
    """Who is publishing, per `git config user.name` in the shared clone.

    Reads git config rather than GIT_AUTHOR_NAME/GIT_COMMITTER_NAME: those
    env vars only affect a new commit's recorded author/committer identity,
    not `git config` lookups. Falls back to "unknown" (never raises) so a
    missing git identity never blocks a publish -- attribution is about
    truthfulness when it IS known, not about requiring one.
    """
    ok, out = run_git(["config", "user.name"], cwd=clone_root)
    author = out.strip() if ok else ""
    return author or "unknown"


@dataclass
class StagedProject:
    """What ``stage_project`` wrote: the number of runs and every file path, for an explicit ``git add``."""

    runs: int
    paths: list[Path] = field(default_factory=list)


def _check_clone_dirs(dest_project_dir: Path, runs: list[Path]) -> None:
    """Refuse a project or run folder in the clone that is a link, before anything is written."""
    if dest_project_dir.is_symlink() or dest_project_dir.parent.is_symlink():
        raise RunArchiveError(f"{dest_project_dir.name} is a link in the shared clone, refusing to publish into it")
    for run_dir in runs:
        if not clone_run_contained(dest_project_dir / run_dir.name):
            raise RunArchiveError(f"run {run_dir.name} is a link in the shared clone, refusing to publish into it")


def stage_project(project_dir: Path, dest_project_dir: Path) -> StagedProject:
    runs = list_completed_runs(project_dir)
    _check_clone_dirs(dest_project_dir, runs)
    ensure_dir(dest_project_dir)
    written: list[Path] = []
    info = read_repository_info(project_dir)
    if info is not None:  # the publisher's folder path never leaves this machine
        replace_json_file(dest_project_dir / _REPO_INFO_FILENAME, published_repository_info(info), indent=2)
        written.append(dest_project_dir / _REPO_INFO_FILENAME)
    # Project-level scan.json (quick-scan coverage metadata: total_files etc.)
    # is consumed by fs_reports._enrich_with_coverage and the project-card
    # coverage reader -- without it, a published clone's dashboard/card never
    # shows a coverage header. Copied only when present; a project scanned
    # before this field existed simply stays absent on the clone too.
    _copy(project_dir / _SCAN_FILENAME, dest_project_dir / _SCAN_FILENAME, written)
    actions = dest_project_dir / ACTIONS_LOG_FILENAME
    merge_actions_log(project_dir / ACTIONS_LOG_FILENAME, actions, actions)
    if actions.is_file():
        written.append(actions)
    for run_dir in runs:
        written.extend(copy_run(run_dir, dest_project_dir / run_dir.name))

    # Record who published and when at publish time,
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
    written.append(dest_project_dir / PUBLISHED_META_FILENAME)
    return StagedProject(len(runs), written)
