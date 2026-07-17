"""Staging logic for publishing a project into the shared results repo.

Pure file operations, no git. Invariants (spec):
- only completed runs (state == "done") are published
- explicit allowlist of source-of-truth files, never derived artifacts
- actions.jsonl is union-merged with the remote copy, never overwritten
"""
from __future__ import annotations

import json
import logging
import shutil
import threading
import time
from pathlib import Path

from quodeq.data.actions_log import ACTIONS_LOG_FILENAME
from quodeq.services.shared_repo import (
    MARKER_FILENAME,
    bootstrap_repo_layout,
    check_repo_format,
    ensure_shared_clone,
    refresh_shared_clone,
    run_git,
)
from quodeq.shared.dimensions_state import FILENAME as DIMENSIONS_FILENAME
from quodeq.shared.run_status import STATUS_FILENAME, UnsupportedSchemaError, read_status

logger = logging.getLogger(__name__)

_RUN_FILES = (STATUS_FILENAME, DIMENSIONS_FILENAME, "events.jsonl")
_EVIDENCE_DIR = "evidence"
_EVALUATION_DIR = "evaluation"


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
    evaluation = run_dir / _EVALUATION_DIR
    if evaluation.is_dir():
        dest_evaluation = dest_run_dir / _EVALUATION_DIR
        dest_evaluation.mkdir(exist_ok=True)
        # Frozen eval-time per-dimension scores (e.g. security.json) are the
        # source of truth read_run_data() needs to render a dashboard at
        # all -- without them a published clone renders an EMPTY dashboard.
        # Pattern-bounded like the evidence glob above: only .json files,
        # nothing else (markdown companions, stray files) from that dir.
        for src in sorted(evaluation.glob("*.json")):
            shutil.copy2(src, dest_evaluation / src.name)


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


_SCAN_FILENAME = "scan.json"


def stage_project(project_dir: Path, dest_project_dir: Path) -> int:
    dest_project_dir.mkdir(parents=True, exist_ok=True)
    info = project_dir / "repository_info.json"
    if info.exists():
        shutil.copy2(info, dest_project_dir / "repository_info.json")
    # Project-level scan.json (quick-scan coverage metadata: total_files etc.)
    # is consumed by _fs_reports._enrich_with_coverage and the project-card
    # coverage reader -- without it, a published clone's dashboard/card never
    # shows a coverage header. Copied only when present; a project scanned
    # before this field existed simply stays absent on the clone too.
    scan = project_dir / _SCAN_FILENAME
    if scan.exists():
        shutil.copy2(scan, dest_project_dir / _SCAN_FILENAME)
    merge_actions_log(
        project_dir / ACTIONS_LOG_FILENAME,
        dest_project_dir / ACTIONS_LOG_FILENAME,
        dest_project_dir / ACTIONS_LOG_FILENAME,
    )
    runs = list_completed_runs(project_dir)
    for run_dir in runs:
        copy_run(run_dir, dest_project_dir / run_dir.name)
    return len(runs)


class PublishError(Exception):
    """User-facing publish failure."""


def _app_version() -> str:
    from quodeq import __version__

    return __version__ or "0.0.0+dev"


def publish_project(
    project_id: str, url: str, *, evaluations_root: Path, env: dict | None = None
) -> int:
    project_dir = evaluations_root / project_id
    if not project_dir.is_dir():
        raise PublishError(f"project {project_id} not found in local evaluations")

    repo = ensure_shared_clone(url, env)
    if repo is None:
        raise PublishError(
            f"could not reach the shared repository, check that git can access {url}"
        )
    refresh_shared_clone(url, env)  # best effort, publish is still guarded by push

    fmt = check_repo_format(repo)
    if fmt == "unsupported_version":
        raise PublishError("this shared repository requires a newer version of quodeq")
    if fmt == "foreign":
        raise PublishError(
            "the configured repository does not look like a quodeq results repository, "
            "refusing to publish into it"
        )
    try:
        if fmt == "empty":
            bootstrap_repo_layout(repo)

        count = stage_project(project_dir, repo / "evaluations" / project_id)
    except (OSError, ValueError) as exc:
        raise PublishError(f"failed to stage project files, {exc}") from exc

    add_paths = [MARKER_FILENAME, ".gitignore", f"evaluations/{project_id}"]
    if (repo / "evaluations" / ".gitkeep").exists():
        add_paths.append("evaluations/.gitkeep")
    ok, out = run_git(["add", "--", *add_paths], cwd=repo)
    if not ok:
        raise PublishError(f"git add failed, {out.strip()[:300]}")

    # A clean `diff --cached` only means nothing NEW was staged this call; it
    # does not mean the remote already has our commits. A prior publish can
    # have committed locally and then failed to push (transient network
    # error), leaving a local commit the remote never received. Retrying
    # with unchanged project files hits this exact "nothing staged" state,
    # so we must still fall through to the push below rather than returning
    # early. A push with nothing new to send exits 0 ("Everything
    # up-to-date"), so this stays a no-op for the true idempotent case.
    nothing_staged, _ = run_git(["diff", "--cached", "--quiet"], cwd=repo)
    if not nothing_staged:
        message = f"Publish {project_id} ({count} runs) via quodeq {_app_version()}"
        ok, out = run_git(["commit", "-m", message], cwd=repo)
        if not ok:
            raise PublishError(f"git commit failed, {out.strip()[:300]}")

    ok, out = _push(repo)
    if not ok:
        ok_rebase, out_rebase = run_git(["pull", "--rebase", "origin", "HEAD"], cwd=repo)
        if ok_rebase:
            ok, out = _push(repo)
        else:
            # A real conflict wedges the persistent clone with a lingering
            # .git/rebase-merge directory, breaking every future publish.
            # The clone is reused across calls, so always leave it clean.
            run_git(["rebase", "--abort"], cwd=repo)
            out = out_rebase
    if not ok:
        raise PublishError(
            f"push to the shared repository failed, try again. {out.strip()[:300]}"
        )
    return count


def _push(repo: Path) -> tuple[bool, str]:
    """Push HEAD to the remote's default branch.

    A fresh --depth 1 clone of a brand-new empty bare repo has no commits
    and no origin/HEAD symref yet, so plain ``push origin HEAD`` has nothing
    to compare against. Detect that case and push with an explicit refspec
    instead, deriving the target branch name from the remote's symref (or
    falling back to the local clone's current branch name).
    """
    ok, out = run_git(["push", "origin", "HEAD"], cwd=repo)
    if ok:
        return ok, out

    # Fall back for a still-unborn remote default branch: push HEAD to an
    # explicit ref name rather than relying on origin/HEAD resolution.
    branch = _remote_default_branch(repo) or _local_branch_name(repo)
    return run_git(["push", "origin", f"HEAD:refs/heads/{branch}"], cwd=repo)


def _remote_default_branch(repo: Path) -> str | None:
    ok, out = run_git(["ls-remote", "--symref", "origin", "HEAD"], cwd=repo)
    if not ok:
        return None
    for line in out.splitlines():
        if line.startswith("ref:"):
            # "ref: refs/heads/main\tHEAD"
            ref = line.split()[1]
            if ref.startswith("refs/heads/"):
                return ref[len("refs/heads/") :]
    return None


def _local_branch_name(repo: Path) -> str:
    ok, out = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    name = out.strip()
    return name if ok and name and name != "HEAD" else "main"


_STATUS_LOCK = threading.Lock()
_STATUS: dict = {
    "state": "idle",
    "project": None,
    "runs": None,
    "error": None,
    "finished_at": None,
}


def get_publish_status() -> dict:
    with _STATUS_LOCK:
        return dict(_STATUS)


def _run_publish(project_id: str, url: str, evaluations_root: Path) -> None:
    try:
        count = publish_project(project_id, url, evaluations_root=evaluations_root)
        with _STATUS_LOCK:
            _STATUS.update(
                state="done", runs=count, error=None, finished_at=time.time()
            )
    except PublishError as exc:
        with _STATUS_LOCK:
            _STATUS.update(state="error", error=str(exc), finished_at=time.time())
    except Exception as exc:  # never leave the job stuck in "running"
        logger.exception("unexpected publish failure")
        with _STATUS_LOCK:
            _STATUS.update(state="error", error=str(exc), finished_at=time.time())


def start_publish(project_id: str, url: str, *, evaluations_root: Path) -> bool:
    with _STATUS_LOCK:
        if _STATUS["state"] == "running":
            return False
        _STATUS.update(
            state="running", project=project_id, runs=None, error=None, finished_at=None
        )
    try:
        thread = threading.Thread(
            target=_run_publish, args=(project_id, url, evaluations_root), daemon=True
        )
        thread.start()
    except Exception as exc:
        with _STATUS_LOCK:
            _STATUS.update(state="error", error=str(exc), finished_at=time.time())
        logger.exception("failed to start publish thread")
        return False
    return True
