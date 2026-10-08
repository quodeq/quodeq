"""GET-route salvage scoring waits for a cancelled run's process to exit.

status.json turns cancelled in the run's SIGTERM handler, while the process
still writes its own cancel-time reports. Scoring then would race it. The
hold-off only lasts as long as a cancel can: after that the pid is reused.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

from quodeq.core.run.job_status import JobStatus
from quodeq.core.types import JobSnapshot
from quodeq.services.score_run import score_terminal_run_once
from quodeq.services.scored_jobs_registry import ScoringClaims


class _Runner:
    def __init__(self) -> None:
        self.submitted: list[str] = []

    def submit(self, fn, *, name=""):
        self.submitted.append(name)
        return True


def _cancelled_run(tmp_path, pid: int) -> JobSnapshot:
    run_dir = tmp_path / "proj" / "run"
    run_dir.mkdir(parents=True)
    (run_dir / ".pid").write_text(str(pid))
    (run_dir / "status.json").write_text('{"state": "cancelled"}')
    return JobSnapshot(job_id="ext-run", status=JobStatus.CANCELLED, output_project="proj", output_run_id="run")


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def test_skips_and_releases_the_claim_while_the_process_is_alive(tmp_path):
    job = _cancelled_run(tmp_path, os.getpid())
    runner, claims = _Runner(), ScoringClaims()

    score_terminal_run_once("ext-run", job, runner, str(tmp_path), claims=claims)

    assert runner.submitted == []
    assert claims.claim("ext-run") is True, "the claim must be free for the GET after exit"


def test_scores_once_the_process_is_gone(tmp_path):
    job = _cancelled_run(tmp_path, _dead_pid())
    runner = _Runner()

    score_terminal_run_once("ext-run", job, runner, str(tmp_path), claims=ScoringClaims())

    assert runner.submitted == ["score-ext-run"]


def test_a_stale_pid_reused_by_a_live_process_does_not_block_scoring(tmp_path, monkeypatch):
    """Long after the run went terminal, escalation has SIGKILLed it: a live pid is a reused one."""
    monkeypatch.setenv("QUODEQ_CANCEL_GRACE_S", "0")
    job = _cancelled_run(tmp_path, os.getpid())
    status = tmp_path / "proj" / "run" / "status.json"
    long_ago = time.time() - 3600
    os.utime(status, (long_ago, long_ago))
    runner = _Runner()

    score_terminal_run_once("ext-run", job, runner, str(tmp_path), claims=ScoringClaims())

    assert runner.submitted == ["score-ext-run"]


def test_a_plain_dict_job_is_scored(tmp_path):
    """Some providers return a plain dict snapshot; getattr would read it as no status."""
    _cancelled_run(tmp_path, _dead_pid())
    job = {"status": JobStatus.CANCELLED, "output_project": "proj", "output_run_id": "run"}
    runner = _Runner()

    score_terminal_run_once("ext-run", job, runner, str(tmp_path), claims=ScoringClaims())

    assert runner.submitted == ["score-ext-run"]
