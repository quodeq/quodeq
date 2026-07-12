"""Mixin providing evaluation lifecycle methods for the filesystem provider."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Protocol

from quodeq.core.types import JobSnapshot
from quodeq.services.base import EvaluationOptions, _DEFAULT_MAX_SUBAGENTS, _DEFAULT_TIME_LIMIT
from quodeq.shared.project_resolver import ProjectIdentity, resolve_project_uuid
from quodeq.core.evidence.parser import parse_jsonl_to_evidence, EvidenceContext
from quodeq.core.scoring.engine import score_evidence
from quodeq.services.grade_formula import load_params
from quodeq.analysis.report import write_dimension_report
from quodeq.data.fs.repo_validation import validate_remote_url
from quodeq.services._fs_clone import run_git_clone
from quodeq.services._fs_scan import scan_project
from quodeq.shared._env import get_clones_dir
from quodeq.shared.utils import get_ai_cmd, get_ai_model, is_repo_url, project_name_from_repo

if TYPE_CHECKING:
    from quodeq.services.jobs import JobManager

_logger = logging.getLogger(__name__)

_LOCATION_ONLINE = "online"
_LOCATION_LOCAL = "local"


class EvaluationDispatcher(Protocol):
    """Abstraction for dispatching evaluation work.

    The default implementation spawns a local subprocess via ``JobManager``.
    Replace with a task-queue or remote-worker implementation for horizontal
    scaling (e.g. Celery, cloud functions).
    """

    def dispatch(
        self,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        ai_provider: str | None = None,
        ai_model: str | None = None,
    ) -> JobSnapshot:
        """Submit an evaluation command and return the initial job state."""
        ...


class SubprocessDispatcher:
    """Default dispatcher that delegates to the in-process ``JobManager``."""

    def __init__(self, job_manager: JobManager) -> None:
        self._jobs = job_manager

    def dispatch(
        self,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        ai_provider: str | None = None,
        ai_model: str | None = None,
    ) -> JobSnapshot:
        return self._jobs.start_job(
            cmd, cwd=cwd, env=env,
            ai_provider=ai_provider, ai_model=ai_model,
        )


def _build_evaluate_cmd(
    repo: str, options: EvaluationOptions, reports_dir: str,
) -> list[str]:
    """Build the CLI command list for a V2 evaluation subprocess."""
    reports_abs = str(Path(reports_dir).resolve())
    repo_path = Path(repo)
    repo_arg = repo if is_repo_url(repo) else str(repo_path.resolve())

    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--_evaluate", "evaluate", repo_arg]
    else:
        cmd = [sys.executable, "-m", "quodeq.cli", "evaluate", repo_arg]
    cmd += ["-o", reports_abs]
    if options.dimensions:
        if isinstance(options.dimensions, list):
            cmd += ["-d", ",".join(options.dimensions)]
        else:
            cmd += ["-d", str(options.dimensions)]
    if options.numerical:
        cmd += ["-m", "numerical"]
    if options.max_subagents != _DEFAULT_MAX_SUBAGENTS:
        cmd += ["--n-subagents", str(options.max_subagents)]
    if options.clean_scan:
        cmd += ["--clean-scan"]
    if options.branch:
        cmd += ["--branch", options.branch]
    if options.scope_path:
        cmd += ["--scope", options.scope_path]
    return cmd


def _scan_parent_project(project_dir: Path, reports_path: Path, repo_path: Path) -> None:
    """Scan the parent project directory if it lacks a scan.json."""
    info_path = project_dir / "repository_info.json"
    try:
        parent_uuid = json.loads(info_path.read_text(encoding="utf-8")).get("parent")
        if parent_uuid:
            parent_dir = reports_path / parent_uuid
            if not (parent_dir / "scan.json").exists():
                scan_project(repo_path, output_dir=parent_dir)
    except (json.JSONDecodeError, OSError):
        pass


def _register_project(
    repo: str,
    discipline: str | None,
    reports_dir: str,
    scope_path: str | None = None,
    *,
    clone_dest: str | None = None,
    ephemeral: bool = False,
) -> str:
    """Resolve/register project and run a scan.

    For URL inputs, clones the repo before scanning. Either *clone_dest* (a
    user-chosen parent directory) or *ephemeral=True* must be set when *repo*
    is a URL. Ephemeral clones land under ``~/.quodeq/clones/<uuid>/``.

    For local path inputs, scans in place; *clone_dest* and *ephemeral* are
    ignored.

    Returns the project's UUID.
    """
    is_url = is_repo_url(repo)
    if is_url:
        # SSRF guard: reject private/loopback/link-local hosts before any clone
        # or directory side effects. Mirrors the CLI prepare_repository path so
        # the web API (POST /api/projects) cannot be pointed at internal hosts.
        validate_remote_url(repo)
    if is_url and not ephemeral and clone_dest is None:
        raise ValueError(
            "URL repos require either clone_dest (user-chosen path) or ephemeral=True"
        )
    if is_url and not ephemeral:
        dest = Path(clone_dest)
        if not dest.is_dir():
            raise FileNotFoundError(
                f"clone destination does not exist or is not a directory: {clone_dest}"
            )

    project_name = project_name_from_repo(repo)
    repo_resolved = repo if is_url else str(Path(repo).resolve())
    reports_path = Path(reports_dir)

    project_uuid = resolve_project_uuid(
        reports_path,
        ProjectIdentity(project_name, repo_resolved, discipline, _LOCATION_LOCAL, scope_path=scope_path),
    )
    project_dir = reports_path / project_uuid
    _ensure_onboarding_field(project_dir)

    # Resolve the on-disk path the project will live at.
    if is_url:
        if ephemeral:
            target_path = get_clones_dir() / project_uuid
        else:
            target_path = Path(clone_dest).resolve() / project_name
        target_path.parent.mkdir(parents=True, exist_ok=True)
        # run_git_clone raises CloneError on failure (Task A8). We let it propagate.
        run_git_clone(repo, target_path)
    else:
        target_path = Path(repo_resolved)
        if not target_path.is_dir():
            raise FileNotFoundError(f"Repo path does not exist: {target_path}")

    # Persist the resolved path + ephemeral flag in repository_info.json.
    info_path = project_dir / "repository_info.json"
    info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else {}
    info["path"] = str(target_path.resolve())
    info["location"] = _LOCATION_LOCAL
    info["ephemeral"] = bool(ephemeral)
    info_path.write_text(json.dumps(info, indent=2), encoding="utf-8")

    # Scan now that files are guaranteed on disk.
    scan_project(target_path, output_dir=project_dir)
    if scope_path:
        _scan_parent_project(project_dir, reports_path, target_path)

    return project_uuid


def _ensure_onboarding_field(project_dir: Path) -> None:
    """Add `onboardingCompletedAt: null` to repository_info.json if absent.

    Called from `_register_project` so newly-registered projects start with the
    field set to null. Existing projects without the field get a backfill on
    read (see `_backfill_onboarding_field` in _fs_project_helpers.py).
    """
    info_path = project_dir / "repository_info.json"
    if not info_path.exists():
        return
    try:
        data = json.loads(info_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if "onboardingCompletedAt" in data:
        return
    data["onboardingCompletedAt"] = None
    info_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class FsEvaluationMixin:
    """Evaluation lifecycle collaborator: start, status, cancel, score.

    Can be used as a standalone object (pass ``jobs`` to ``__init__``) or as a
    mixin (set ``self._jobs`` on the host before calling any method).  The
    ``get_status_fn`` hook lets a composing host override the status lookup so
    that external-job IDs (``ext-`` prefix, resolved via SQLite) work correctly
    inside ``cancel_evaluation`` without re-introducing MRO coupling.
    """

    _jobs: JobManager
    _dispatcher: EvaluationDispatcher | None

    def __init__(
        self,
        jobs: JobManager | None = None,
        get_status_fn: Callable | None = None,
    ) -> None:
        if jobs is not None:
            self._jobs = jobs
        self._dispatcher = None
        self._get_status_fn = get_status_fn

    @property
    def dispatcher(self) -> EvaluationDispatcher:
        """Return the evaluation dispatcher, defaulting to subprocess-based."""
        d = getattr(self, "_dispatcher", None)
        if d is not None:
            return d
        return SubprocessDispatcher(self._jobs)

    @staticmethod
    def _build_eval_env(repo: str, options: EvaluationOptions, env: dict[str, str] | None = None) -> dict[str, str]:
        """Build the subprocess environment for an evaluation run."""
        base = env if env is not None else os.environ
        built_env = {**base, "PYTHONUNBUFFERED": "1"}
        built_env["AI_CMD"] = options.ai_cmd or get_ai_cmd()
        ai_model = options.ai_model or get_ai_model()
        subagent_model = options.subagent_model or ai_model
        # Ensure both env vars are set consistently — prevents model swapping
        # between verification (reads AI_MODEL) and analysis (reads SUBAGENT_MODEL)
        if ai_model:
            built_env["AI_MODEL"] = ai_model
        if subagent_model:
            built_env["SUBAGENT_MODEL"] = subagent_model
        if not options.verify_findings:
            built_env["QUODEQ_NO_VERIFY"] = "1"
        # Always propagate a positive limit. The CLI subprocess uses this to
        # set the run-level deadline (lifecycle.set_deadline + analyzing_start
        # marker) that the dashboard's countdown timer depends on. Skipping
        # the default value left dashboard runs with no deadline, freezing
        # the UI timer at the static budget.
        if options.time_limit and options.time_limit > 0:
            built_env["QUODEQ_TIME_LIMIT"] = str(options.time_limit)
        if options.per_dimension:
            built_env["QUODEQ_NO_CONSOLIDATE"] = "1"
        if options.context_size > 0:
            built_env["QUODEQ_CONTEXT_SIZE"] = str(options.context_size)
        if options.ai_cmd == "omlx":
            if options.provider_api_key:
                built_env["OMLX_API_KEY"] = options.provider_api_key
            if options.provider_api_base:
                built_env["OMLX_BASE_URL"] = options.provider_api_base
        return built_env

    def start_evaluation(self, repo: str, reports_dir: str, options: EvaluationOptions) -> JobSnapshot:
        """Start an asynchronous evaluation subprocess for a repository."""
        if is_repo_url(repo):
            raise ValueError(
                "URL repos are not supported here. Register the project via "
                "POST /api/projects (which clones to disk) and pass the local path."
            )
        resolved = Path(repo).resolve()
        if not resolved.exists():
            raise FileNotFoundError(
                f"Repository not found: {repo}. "
                f"Check that the path exists and is accessible from this machine."
            )

        cmd = _build_evaluate_cmd(repo, options, reports_dir)
        _register_project(repo, options.discipline, reports_dir, scope_path=options.scope_path)
        # Keep JobManager aware of the current reports root so _tee_run_log
        # can resolve run.log paths for dashboard-spawned evaluations.
        # Guard with hasattr so custom/stub job managers remain compatible.
        if hasattr(self._jobs, "set_reports_root"):
            self._jobs.set_reports_root(Path(reports_dir))
        env = self._build_eval_env(repo, options)
        # For files, walk up to find git root; for dirs, use as-is
        if resolved.is_file():
            candidate = resolved.parent
            cwd = str(candidate)
            while candidate != candidate.parent:
                if (candidate / ".git").exists():
                    cwd = str(candidate)
                    break
                candidate = candidate.parent
        else:
            cwd = str(resolved)
        return self.dispatcher.dispatch(
            cmd, cwd=cwd, env=env,
            ai_provider=options.ai_cmd,
            ai_model=options.ai_model,
        )

    def get_evaluation_status(self, job_id: str, reports_dir: str | None = None) -> JobSnapshot | None:
        """Return the current status of an evaluation job.

        When a ``get_status_fn`` was injected at construction time, delegates
        to that function (allows a composing host to supply a richer lookup,
        e.g. via ``EvaluationsIndex``, without MRO coupling).  Otherwise falls
        back to ``JobManager.get_job`` which handles the ``ext-`` prefix via
        the filesystem.
        """
        fn = getattr(self, "_get_status_fn", None)
        if fn is not None:
            return fn(job_id, reports_dir=reports_dir)
        reports_root = Path(reports_dir) if reports_dir else None
        return self._jobs.get_job(job_id, reports_root=reports_root)

    def cancel_evaluation(
        self, job_id: str, reports_dir: str | None = None,
        *, discard_partial: bool = False,
    ) -> bool:
        """Cancel a running evaluation job; score completed dims unless discarding.

        Uses ``self.get_evaluation_status`` rather than a bare
        ``self._jobs.get_job`` so that external runs (``ext-`` prefix) also
        resolve correctly via the SQLite index (Plan B1 override on
        ``FilesystemActionProvider``). Before this, ``get_job`` returned
        ``None`` for ``ext-`` ids and the scoring block was dead for them.
        ``_score_completed_evidence`` is idempotent (skips dimensions whose
        report file already exists), so double-firing with the route-level
        scoring in ``_evaluation_routes`` is a no-op.

        After ``cancel_job`` returns we wait briefly for the run lifecycle
        handler in the subprocess to write ``status.json`` to a terminal
        state. Without this wait, the API returns while observers reading
        ``status.json`` (UI dashboard query, SSE stream, etc.) still see
        the run as ``in_progress`` for a window of ~100ms-1s, producing
        the "two running rows" UX after a cancel-then-start.

        When ``discard_partial`` is True the run must end up as if it never
        happened: completed evidence is NOT scored, and the traces the run
        left in shared state (V2 cache entries, evidence scratch) are wiped.
        ``FilesystemActionProvider.cancel_evaluation`` then removes the run
        directory and its index row.
        """
        reports_root = Path(reports_dir) if reports_dir else None
        job = self.get_evaluation_status(job_id, reports_dir=reports_dir)
        ok = self._jobs.cancel_job(job_id, reports_root=reports_root)
        if ok and reports_dir and job:
            run_dir = Path(reports_dir) / job.output_project / job.output_run_id
            _wait_for_terminal_status(run_dir)
            if discard_partial:
                _discard_run_state(reports_dir, {
                    "outputProject": job.output_project,
                    "outputRunId": job.output_run_id,
                })
            else:
                _score_completed_evidence(reports_dir, {
                    "outputProject": job.output_project,
                    "outputRunId": job.output_run_id,
                })
        return ok

    def score_failed_evaluation(self, job_id: str, reports_dir: str) -> bool:
        """Score any completed dimensions from a failed evaluation."""
        job = self._jobs.get_job(job_id)
        if not job or job.get("status") not in ("failed", "cancelled"):
            return False
        _score_completed_evidence(reports_dir, job)
        return True

    def list_evaluations(
        self,
        *,
        limit: int = 0,
        reports_dir: str | None = None,
        states: set[str] | None = None,
    ) -> list[JobSnapshot]:
        """Return evaluation jobs (running, done, failed, cancelled).

        When *limit* > 0 only the most recent *limit* jobs are returned.
        When *reports_dir* is provided, external in-progress runs are merged in.
        When *states* is provided, only jobs with status in the set are returned.
        """
        reports_root = Path(reports_dir) if reports_dir else None
        jobs = self._jobs.list_jobs(reports_root=reports_root)
        if states:
            jobs = [j for j in jobs if j.status in states]
        return jobs[:limit] if limit > 0 else jobs


_TERMINAL_RUN_STATES = frozenset({"done", "failed", "cancelled"})
_CANCEL_WAIT_TIMEOUT_S = 2.0
_CANCEL_WAIT_POLL_S = 0.05


def _wait_for_terminal_status(
    run_dir: Path,
    *,
    timeout_s: float = _CANCEL_WAIT_TIMEOUT_S,
    poll_interval_s: float = _CANCEL_WAIT_POLL_S,
) -> bool:
    """Block until ``run_dir/status.json`` reports a terminal state, or timeout.

    Returns True when a terminal state ({done, failed, cancelled}) is
    observed on disk; returns False on timeout. Best-effort: a False
    return does not abort the calling cancel flow — downstream polling
    or SSE will eventually catch up.

    Bridges the async gap between ``JobManager.cancel_job`` returning
    (in-memory state flipped, signal sent to subprocess) and the run
    lifecycle handler in the subprocess flushing ``status.json`` to
    terminal. Without this wait, observers reading from disk
    immediately after the API returns can still see the run as
    ``in_progress`` for ~100ms-1s, producing a window where a
    follow-up "Start" surfaces two ``running`` rows in the UI.
    """
    deadline = time.monotonic() + timeout_s
    status_path = run_dir / "status.json"
    while True:
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("state") in _TERMINAL_RUN_STATES:
                return True
        except (OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval_s)


def _open_cache():
    """Indirection so tests can swap in a fake backend."""
    from quodeq.analysis.cache import LocalFileBackend
    return LocalFileBackend()


def _discard_run_state(reports_dir: str, job: dict) -> None:
    """Wipe every trace a discarded run left behind.

    Invoked when the user cancels with "Discard findings": the run must end
    up as if it never happened. For EVERY dim that dispatched work (has a
    ``<dim>_dispatch_keys.json`` sidecar) the V2 content-addressed cache
    entries it wrote are deleted, including dims that finished cleanly.
    Without that, the next incremental run counts the discarded run's files
    as "analyzed in previous runs" in the coverage header. The sidecar holds
    only this run's dispatched (cache-miss) keys, so entries written by
    earlier kept runs are not touched.

    All per-dim scratch (queue, fingerprint, evidence JSONL, sidecar) is
    removed so the status-GET scoring path cannot resurrect a report from
    leftover evidence. The caller removes the run directory itself.
    """
    project = job.get("outputProject")
    run_id = job.get("outputRunId")
    if not project or not run_id:
        return

    run_dir = Path(reports_dir) / project / run_id
    evidence_dir = run_dir / "evidence"
    if not evidence_dir.is_dir():
        return

    cache = None
    for sidecar in evidence_dir.glob("*_dispatch_keys.json"):
        try:
            keys = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _logger.warning("Could not read sidecar %s: %s", sidecar, exc)
            continue
        if not isinstance(keys, dict):
            continue
        if cache is None:
            cache = _open_cache()
        for key in keys.values():
            try:
                cache.delete(key)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("Could not delete cache entry %s: %s", key, exc)

    scratch_patterns = (
        "*_queue.json", "*_fingerprint.json",
        "*_evidence.jsonl", "*_dispatch_keys.json",
    )
    for pattern in scratch_patterns:
        for victim in evidence_dir.glob(pattern):
            try:
                victim.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                _logger.warning("Could not discard %s: %s", victim, exc)


def _read_queue_files_count(queue_path: Path) -> int:
    """Sum of files dispatched across all batches in a dim's queue.json.

    Used to populate ``files_read`` when scoring residual evidence —
    without this, ``_score_completed_evidence`` writes eval stubs with
    ``filesRead: 0``, which the ``scoring_view`` trust rule rejects as
    untrustworthy. Returning the queue's taken count yields a faithful
    coverage figure: every file that was actually dispatched to an agent.
    """
    try:
        data = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return 0
    taken = data.get("taken") if isinstance(data, dict) else None
    if not isinstance(taken, list):
        return 0
    total = 0
    for entry in taken:
        files = entry.get("files") if isinstance(entry, dict) else None
        if isinstance(files, list):
            total += len(files)
    return total


def _read_project_source_file_count(reports_dir: str, project: str) -> int:
    """Read ``scan.json`` total_files for the project. Returns 0 on failure."""
    scan_path = Path(reports_dir) / project / "scan.json"
    try:
        data = json.loads(scan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return 0
    raw = data.get("total_files") if isinstance(data, dict) else None
    return int(raw) if isinstance(raw, int) else 0


def _score_completed_evidence(reports_dir: str, job: dict) -> None:
    """Score any dimensions that have evidence but no evaluation report.

    Called after cancellation so completed dimensions are preserved in the
    dashboard even when the overall run was cancelled.

    Populates ``files_read`` from the dim's queue.json (count of dispatched
    files) and ``source_file_count`` from the project's scan.json. Without
    these, the scored eval has ``filesRead: 0``, which ``scoring_view``'s
    trust rule rejects — the user sees the cancelled run's data fall
    through to an older run's stale value despite real findings on disk.
    """
    project = job.get("outputProject")
    run_id = job.get("outputRunId")
    if not project or not run_id:
        return

    _log = _logger

    evidence_dir = Path(reports_dir) / project / run_id / "evidence"
    evaluation_dir = Path(reports_dir) / project / run_id / "evaluation"
    if not evidence_dir.is_dir():
        return

    evaluation_dir.mkdir(parents=True, exist_ok=True)
    source_file_count = _read_project_source_file_count(reports_dir, project)
    params = load_params()

    from quodeq.shared.dimensions_state import read_dimensions
    dim_states = read_dimensions(Path(reports_dir) / project / run_id).get("dimensions", {})

    for jsonl_path in evidence_dir.glob("*_evidence.jsonl"):
        dim_id = jsonl_path.name.replace("_evidence.jsonl", "")
        eval_file = evaluation_dir / f"{dim_id}.json"
        if eval_file.exists():
            continue  # already scored
        if dim_states.get(dim_id, {}).get("state") == "incomplete":
            _logger.info("Skipping scoring for incomplete dim %s", dim_id)
            continue
        if jsonl_path.stat().st_size == 0:
            continue  # no findings
        # Only score dimensions that passed verification (analysis queue exists)
        queue_file = evidence_dir / f"{dim_id}_queue.json"
        if not queue_file.exists():
            continue  # verification not completed for this dimension

        files_read = _read_queue_files_count(queue_file)
        try:
            evidence = parse_jsonl_to_evidence(jsonl_path, EvidenceContext(
                language="", repository="", date_str="",
                source_file_count=source_file_count, files_read=files_read,
            ))
            if evidence is None:
                continue
            scores = score_evidence(evidence, mode="numerical", params=params)
            write_dimension_report(evidence, scores, dim_id, evaluation_dir)
            _log.info(
                "Scored cancelled dimension '%s' for run %s (files_read=%d)",
                dim_id, run_id[:8], files_read,
            )
        except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
            _log.debug("Could not score cancelled dimension '%s': %s", dim_id, exc)
