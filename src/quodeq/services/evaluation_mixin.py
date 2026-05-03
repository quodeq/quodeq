"""Mixin providing evaluation lifecycle methods for the filesystem provider."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from quodeq.core.types import JobSnapshot
from quodeq.services.base import EvaluationOptions, _DEFAULT_MAX_SUBAGENTS, _DEFAULT_TIME_LIMIT
from quodeq.shared.project_resolver import ProjectIdentity, resolve_project_uuid
from quodeq.shared.repo_handler import is_valid_repo_url
from quodeq.core.evidence.parser import parse_jsonl_to_evidence, EvidenceContext
from quodeq.core.scoring.engine import score_evidence
from quodeq.analysis.report import write_dimension_report
from quodeq.services._fs_scan import scan_project
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
    ) -> JobSnapshot:
        return self._jobs.start_job(cmd, cwd=cwd, env=env)


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
    if options.incremental:
        cmd += ["--incremental"]
    if options.branch:
        cmd += ["--branch", options.branch]
    if options.scope_path:
        cmd += ["--scope", options.scope_path]
    return cmd


def _scan_parent_project(project_dir: Path, reports_path: Path, repo_path: Path) -> None:
    """Scan the parent project directory if it lacks a scan.json."""
    info_path = project_dir / "repository_info.json"
    try:
        parent_uuid = json.loads(info_path.read_text()).get("parent")
        if parent_uuid:
            parent_dir = reports_path / parent_uuid
            if not (parent_dir / "scan.json").exists():
                scan_project(repo_path, output_dir=parent_dir)
    except (json.JSONDecodeError, OSError):
        pass


def _register_project(repo: str, discipline: str | None, reports_dir: str, scope_path: str | None = None) -> str:
    """Resolve/register project and run a scan for local projects.

    For scoped evaluations, registers parent first, scans it, then registers
    the child so both exist with scan data before the evaluation starts.

    Returns the project's UUID.
    """
    repo_resolved = str(Path(repo).resolve()) if not is_repo_url(repo) else repo
    project_name = project_name_from_repo(repo)
    location = _LOCATION_ONLINE if is_repo_url(repo) else _LOCATION_LOCAL
    reports_path = Path(reports_dir)

    project_uuid = resolve_project_uuid(
        reports_path,
        ProjectIdentity(project_name, repo_resolved, discipline, location, scope_path=scope_path),
    )

    # Mark this project as needing onboarding completion (Phase 2 of the
    # onboarding wizard). The field is set to `null` on first registration
    # and rewritten to an ISO-8601 timestamp the first time an evaluation
    # successfully starts against this project (see _mark_onboarding_completed).
    _ensure_onboarding_field(reports_path / project_uuid)

    # Scan local projects so file lists are available immediately
    if location == _LOCATION_LOCAL:
        repo_path = Path(repo_resolved)
        if repo_path.is_dir():
            project_dir = reports_path / project_uuid
            scan_project(repo_path, output_dir=project_dir)
            # For scoped projects, also scan the parent using the parent UUID from repo info
            if scope_path:
                _scan_parent_project(project_dir, reports_path, repo_path)

    return project_uuid


def _ensure_onboarding_field(project_dir: Path) -> None:
    """Add `onboardingCompletedAt: null` to repository_info.json if absent.

    Called from `_register_project` so newly-registered projects start with the
    field set to null. Existing projects without the field get a backfill on
    read (see `_backfill_onboarding_field` in routes_project_data.py).
    """
    info_path = project_dir / "repository_info.json"
    if not info_path.exists():
        return
    try:
        data = json.loads(info_path.read_text())
    except (json.JSONDecodeError, OSError):
        return
    if "onboardingCompletedAt" in data:
        return
    data["onboardingCompletedAt"] = None
    info_path.write_text(json.dumps(data, indent=2))


class FsEvaluationMixin:
    """Mixin for evaluation start/status/cancel methods.

    Requires the host class to provide a ``_jobs`` attribute (a ``JobManager``)
    and optionally a ``_dispatcher`` attribute (an ``EvaluationDispatcher``).
    When no dispatcher is set, a ``SubprocessDispatcher`` wrapping ``_jobs``
    is used automatically.
    """

    _jobs: JobManager
    _dispatcher: EvaluationDispatcher | None

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
        if options.time_limit != _DEFAULT_TIME_LIMIT:
            built_env["QUODEQ_TIME_LIMIT"] = str(options.time_limit)
        if options.per_dimension:
            built_env["QUODEQ_NO_CONSOLIDATE"] = "1"
        if options.context_size > 0:
            built_env["QUODEQ_CONTEXT_SIZE"] = str(options.context_size)
        return built_env

    def start_evaluation(self, repo: str, reports_dir: str, options: EvaluationOptions) -> JobSnapshot:
        """Start an asynchronous evaluation subprocess for a repository."""
        if is_repo_url(repo):
            if not is_valid_repo_url(repo):
                raise ValueError(
                    f"Invalid repository URL format: {repo}. "
                    f"Expected a URL like https://github.com/owner/repo or git@github.com:owner/repo.git"
                )
        else:
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
        if is_repo_url(repo):
            cwd = str(Path.cwd())
        else:
            resolved = Path(repo).resolve()
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
        return self.dispatcher.dispatch(cmd, cwd=cwd, env=env)

    def get_evaluation_status(self, job_id: str, reports_dir: str | None = None) -> JobSnapshot | None:
        """Return the current status of an evaluation job.

        Passes *reports_dir* to ``JobManager.get_job`` so that external jobs
        (``ext-`` prefix) can be looked up from the filesystem.
        """
        reports_root = Path(reports_dir) if reports_dir else None
        return self._jobs.get_job(job_id, reports_root=reports_root)

    def cancel_evaluation(
        self, job_id: str, reports_dir: str | None = None,
        *, discard_partial: bool = False,
    ) -> bool:
        """Cancel a running evaluation job and score any completed dimensions.

        Uses ``self.get_evaluation_status`` rather than a bare
        ``self._jobs.get_job`` so that external runs (``ext-`` prefix) also
        resolve correctly via the SQLite index (Plan B1 override on
        ``FilesystemActionProvider``). Before this, ``get_job`` returned
        ``None`` for ``ext-`` ids and the scoring block was dead for them.
        ``_score_completed_evidence`` is idempotent (skips dimensions whose
        report file already exists), so double-firing with the route-level
        scoring in ``_evaluation_routes`` is a no-op.

        When ``discard_partial`` is True we also wipe queue + fingerprint
        files for any dim that didn't complete scoring — the next run sees
        no salvageable state and starts fresh for those dims.
        """
        reports_root = Path(reports_dir) if reports_dir else None
        job = self.get_evaluation_status(job_id, reports_dir=reports_dir)
        ok = self._jobs.cancel_job(job_id, reports_root=reports_root)
        if ok and reports_dir and job:
            _score_completed_evidence(reports_dir, {
                "outputProject": job.output_project,
                "outputRunId": job.output_run_id,
            })
            if discard_partial:
                _discard_partial_dim_state(reports_dir, {
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


def _discard_partial_dim_state(reports_dir: str, job: dict) -> None:
    """Wipe queue + fingerprint files for any dim that didn't finish scoring.

    Invoked when the user opts to discard collected findings on cancel.
    Dims with ``evaluation/<dim>.json`` (cleanly scored) are preserved —
    only in-flight ones are reset, so partial work doesn't get accidentally
    discarded just because the umbrella run was stopped.
    """
    project = job.get("outputProject")
    run_id = job.get("outputRunId")
    if not project or not run_id:
        return

    evidence_dir = Path(reports_dir) / project / run_id / "evidence"
    evaluation_dir = Path(reports_dir) / project / run_id / "evaluation"
    if not evidence_dir.is_dir():
        return

    scored_dims: set[str] = set()
    if evaluation_dir.is_dir():
        for eval_file in evaluation_dir.glob("*.json"):
            scored_dims.add(eval_file.stem)

    for queue_path in evidence_dir.glob("*_queue.json"):
        dim_id = queue_path.name.replace("_queue.json", "")
        if dim_id in scored_dims:
            continue
        for victim in (queue_path, evidence_dir / f"{dim_id}_fingerprint.json"):
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

    for jsonl_path in evidence_dir.glob("*_evidence.jsonl"):
        dim_id = jsonl_path.name.replace("_evidence.jsonl", "")
        eval_file = evaluation_dir / f"{dim_id}.json"
        if eval_file.exists():
            continue  # already scored
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
            scores = score_evidence(evidence, mode="numerical")
            write_dimension_report(evidence, scores, dim_id, evaluation_dir)
            _log.info(
                "Scored cancelled dimension '%s' for run %s (files_read=%d)",
                dim_id, run_id[:8], files_read,
            )
        except (OSError, json.JSONDecodeError, ValueError, KeyError) as exc:
            _log.debug("Could not score cancelled dimension '%s': %s", dim_id, exc)
