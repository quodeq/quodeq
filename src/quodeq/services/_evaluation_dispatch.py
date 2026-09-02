"""Evaluation dispatch: the subprocess-launch abstraction and CLI command builder.

Split (Task 14) out of ``evaluation_mixin.py``: ``EvaluationDispatcher`` is the
injection seam for how an evaluation command actually gets run (the default
``SubprocessDispatcher`` spawns it via ``JobManager``); ``_build_evaluate_cmd``
turns an ``EvaluationOptions`` into the CLI argv. Re-exported by
``evaluation_mixin.py`` (tests import both names from there).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from quodeq.core.types import JobSnapshot
from quodeq.services.base import EvaluationOptions, DEFAULT_MAX_SUBAGENTS
from quodeq.shared.utils import is_repo_url

if TYPE_CHECKING:
    from quodeq.services.jobs import JobManager


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
        time_limit_s: int | None = None,
    ) -> JobSnapshot:
        """Submit an evaluation command and return the initial job state."""
        ...


class SubprocessDispatcher:
    """Default dispatcher that delegates to the in-process ``JobManager``."""

    def __init__(self, job_manager: "JobManager") -> None:
        self._jobs = job_manager

    def dispatch(
        self,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        ai_provider: str | None = None,
        ai_model: str | None = None,
        time_limit_s: int | None = None,
    ) -> JobSnapshot:
        return self._jobs.start_job(
            cmd, cwd=cwd, env=env,
            ai_provider=ai_provider, ai_model=ai_model,
            time_limit_s=time_limit_s,
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
    if options.max_subagents != DEFAULT_MAX_SUBAGENTS:
        cmd += ["--n-subagents", str(options.max_subagents)]
    if options.clean_scan:
        cmd += ["--clean-scan"]
    if options.branch:
        cmd += ["--branch", options.branch]
    if options.scope_path:
        cmd += ["--scope", options.scope_path]
    return cmd
