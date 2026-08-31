"""Staging logic for publishing a project into the shared results repo.

Mostly pure file operations; the one exception is a `git config user.name`
read (stage_project writes published.json, see audit finding C1). Invariants
(spec):
- only completed runs (state == "done") are published
- explicit allowlist of source-of-truth files, never derived artifacts
- actions.jsonl is union-merged with the remote copy, never overwritten
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from quodeq.services._wiring import (
    ACTIONS_LOG_FILENAME,
    DIMENSIONS_FILENAME,
    MARKER_FILENAME,
    PUBLISHED_META_FILENAME,
    STATUS_FILENAME,
    UnsupportedSchemaError,
    bootstrap_repo_layout,
    check_repo_format,
    clone_lock,
    copy_file_if_exists,
    copy_matching_files,
    ensure_dir,
    ensure_shared_clone,
    read_status,
    refresh_shared_clone,
    replace_json_file,
    run_git,
)
from quodeq.shared.validation import validate_path_segment

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


_SCAN_FILENAME = "scan.json"


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


class PublishError(Exception):
    """User-facing publish failure."""


def _app_version() -> str:
    from quodeq import __version__

    return __version__ or "0.0.0+dev"


def publish_project(
    project_id: str, url: str, *, evaluations_root: Path, env: dict | None = None
) -> int:
    # The route validates too, but this is the last stop before project_id
    # becomes a filesystem path and a git pathspec, so guard it here as well.
    try:
        validate_path_segment(project_id)
    except ValueError as exc:
        raise PublishError(str(exc)) from exc
    project_dir = evaluations_root / project_id
    if not project_dir.is_dir():
        raise PublishError(f"project {project_id} not found in local evaluations")

    # Everything from here through the final push/rebase runs under one
    # process-wide clone lock (audit finding C2): a background refresh
    # racing this stage/commit/push on the same clone directory can tear a
    # commit or contend on .git/index.lock. clone_lock is an RLock, so the
    # ensure_shared_clone / refresh_shared_clone calls below (each of which
    # acquires it again internally) reenter on this same thread instead of
    # deadlocking.
    with clone_lock(url, env):
        repo = ensure_shared_clone(url, env)
        if repo is None:
            raise PublishError(
                f"could not reach the shared repository, check that git can access {url}"
            )
        ok, _ = refresh_shared_clone(url, env)  # best effort, publish is still guarded by push

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

        # stage_project unconditionally rewrites published.json with a fresh
        # publishedAt/publishedBy (needed so those fields DO advance when
        # content really changes). That means an otherwise-unchanged
        # republish still stages a one-line diff on that file alone once the
        # wall clock ticks to a new second. Detect that "staged set is only
        # published.json" case and revert it to HEAD before the nothing-staged
        # check below, so attribution only updates when real project content
        # changed. A project's first-ever publish can never hit this
        # incorrectly: published.json isn't in HEAD yet, so the staged set
        # always includes the new runs/info files alongside it too. If it
        # somehow doesn't, the checkout below simply fails against a
        # nonexistent HEAD path; that failure is ignored and the normal
        # commit path proceeds as if nothing special happened.
        published_rel = f"evaluations/{project_id}/{PUBLISHED_META_FILENAME}"
        ok_names, names_out = run_git(["diff", "--cached", "--name-only"], cwd=repo)
        staged_names = [line.strip() for line in names_out.splitlines() if line.strip()]
        if ok_names and staged_names == [published_rel]:
            run_git(["checkout", "HEAD", "--", published_rel], cwd=repo)

        # A clean `diff --cached` only means nothing NEW was staged this
        # call; it does not mean the remote already has our commits. A
        # prior publish can have committed locally and then failed to push
        # (transient network error), leaving a local commit the remote never
        # received. Retrying with unchanged project files hits this exact
        # "nothing staged" state, so we must still fall through to the push
        # below rather than returning early. A push with nothing new to
        # send exits 0 ("Everything up-to-date"), so this stays a no-op for
        # the true idempotent case.
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
                # A real conflict wedges the persistent clone with a
                # lingering .git/rebase-merge directory, breaking every
                # future publish. The clone is reused across calls, so
                # always leave it clean.
                run_git(["rebase", "--abort"], cwd=repo)
                out = out_rebase
        if not ok:
            raise PublishError(
                f"push to the shared repository failed, try again. {out.strip()[:300]}"
            )
        return count


def _push(repo: Path) -> tuple[bool, str]:
    """Push HEAD to the remote's default branch.

    A fresh clone of a brand-new empty bare repo has no commits and no
    origin/HEAD symref yet, so plain ``push origin HEAD`` has nothing
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


class PublishStatus:
    """Lock-guarded publish job status (states: idle/running/done/error).

    Instantiable so tests get isolated status; production shares the
    module-default instance below — a single global publish slot.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status: dict = {
            "state": "idle",
            "project": None,
            "runs": None,
            "error": None,
            "finished_at": None,
        }

    def copy(self) -> dict:
        with self._lock:
            return dict(self._status)

    def set(self, **fields) -> None:
        with self._lock:
            self._status.update(fields)

    def claim(self, project_id: str) -> bool:
        """Atomically take the publish slot; False when a publish is running."""
        with self._lock:
            if self._status["state"] == "running":
                return False
            self._status.update(
                state="running", project=project_id, runs=None, error=None,
                finished_at=None,
            )
            return True


_default_status = PublishStatus()


def get_publish_status(status: PublishStatus | None = None) -> dict:
    return (status or _default_status).copy()


def _run_publish(
    project_id: str, url: str, evaluations_root: Path, status: PublishStatus,
) -> None:
    try:
        count = publish_project(project_id, url, evaluations_root=evaluations_root)
        status.set(state="done", runs=count, error=None, finished_at=time.time())
    except PublishError as exc:
        status.set(state="error", error=str(exc), finished_at=time.time())
    except Exception as exc:  # never leave the job stuck in "running"
        logger.exception("unexpected publish failure")
        status.set(state="error", error=str(exc), finished_at=time.time())


def start_publish(
    project_id: str, url: str, *,
    evaluations_root: Path,
    status: PublishStatus | None = None,
) -> str:
    """Kick off a background publish.

    Returns "started", "already_running" (another publish holds the slot),
    or "failed" (the worker thread could not be started; the status dict
    carries the error). Callers must not collapse the last two: one is a
    409-style conflict, the other a server-side failure.
    """
    status = status or _default_status
    if not status.claim(project_id):
        return "already_running"
    try:
        thread = threading.Thread(
            target=_run_publish, args=(project_id, url, evaluations_root, status),
            daemon=True,
        )
        thread.start()
    except Exception as exc:
        status.set(state="error", error=str(exc), finished_at=time.time())
        logger.exception("failed to start publish thread")
        return "failed"
    return "started"
