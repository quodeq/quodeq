"""The external-run cancel returns without waiting out the SIGTERM grace window.

The cancel route calls this on a Flask request thread; waiting the grace
window (30s by default) plus the SIGKILL settle there held the worker for the
whole time a run took to die. Only SIGTERM is sent inline now. Keep-findings
scoring waits for the process to be gone: until then it is still writing its
own cancel-time reports.
"""
from __future__ import annotations

import os
import signal
import threading
import time
from pathlib import Path
from unittest.mock import patch

from quodeq.core.types import JobSnapshot
from quodeq.services.evaluation_mixin import FsEvaluationMixin
from quodeq.services.jobs import InMemoryJobStore, JobManager, JobProcessSeams
from tests._timeouts import budget

_GRACE_S = 3.0
_SCORE = "quodeq.services.evaluation_mixin.score_completed_evidence"
_WAIT_TERMINAL = "quodeq.services.evaluation_mixin.wait_for_terminal_status"


def _write_pid(tmp_path) -> Path:
    # A live pid, so the .pid lookup accepts it; the stub control never signals it.
    run_dir = tmp_path / "proj" / "run"
    run_dir.mkdir(parents=True)
    (run_dir / ".pid").write_text(str(os.getpid()))
    return run_dir


class _StubbornProcess:
    """Duck-typed process control: the pid ignores SIGTERM and dies on the escalation."""

    def __init__(self) -> None:
        self.signals: list[int] = []
        self.killed = threading.Event()
        self.threads: list[threading.Thread] = []

    def kill_tree(self, _pid: int, sig: int) -> None:
        # The second signal is the escalation (SIGKILL; SIGTERM again on Windows).
        self.signals.append(sig)
        if len(self.signals) > 1:
            self.killed.set()

    def pid_alive(self, _pid: int) -> bool:
        return not self.killed.is_set()

    def start_background(self, fn, name) -> None:
        thread = threading.Thread(target=fn, name=name, daemon=True)
        self.threads.append(thread)
        thread.start()


def _manager(proc: _StubbornProcess) -> JobManager:
    return JobManager(JobProcessSeams(process_control=proc), job_store=InMemoryJobStore())


def test_cancel_returns_before_the_grace_window_and_escalates_in_the_background(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_CANCEL_GRACE_S", str(_GRACE_S))
    _write_pid(tmp_path)
    proc = _StubbornProcess()

    start = time.monotonic()
    result = _manager(proc).cancel_job("ext-run", reports_root=tmp_path)
    elapsed = time.monotonic() - start

    assert result is True
    assert elapsed < _GRACE_S / 3, f"cancel blocked {elapsed:.2f}s on a {_GRACE_S}s grace window"
    assert proc.signals == [signal.SIGTERM]
    assert len(proc.threads) == 1
    proc.threads[0].join(timeout=budget(_GRACE_S + 5))
    assert len(proc.signals) == 2, "the background thread never escalated"


def test_wait_for_exit_blocks_until_the_process_is_gone(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_CANCEL_GRACE_S", "0.05")
    _write_pid(tmp_path)
    proc = _StubbornProcess()

    result = _manager(proc).cancel_job("ext-run", reports_root=tmp_path, wait_for_exit=True)

    assert result is True
    assert len(proc.signals) == 2
    assert proc.threads == [], "wait_for_exit must escalate inline"


def test_keep_findings_cancel_scores_only_after_the_process_exits(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_CANCEL_GRACE_S", "0.3")
    _write_pid(tmp_path)
    proc = _StubbornProcess()
    mixin = FsEvaluationMixin()
    mixin._jobs = _manager(proc)
    snapshot = JobSnapshot(job_id="ext-run", status="running", output_project="proj", output_run_id="run")
    alive_when_scored: list[bool] = []

    with patch.object(FsEvaluationMixin, "get_evaluation_status", return_value=snapshot), \
         patch(_WAIT_TERMINAL), \
         patch(_SCORE, side_effect=lambda *_a: alive_when_scored.append(proc.pid_alive(0))):
        assert mixin.cancel_evaluation("ext-run", reports_dir=str(tmp_path)) is True
        assert alive_when_scored == [], "scored while the process was still inside its grace window"
        proc.threads[0].join(timeout=budget(5))

    assert alive_when_scored == [False]


def test_wait_for_exit_cancel_scores_before_it_returns(tmp_path, monkeypatch):
    """The window close's ?wait=true: scoring must be done when the call returns."""
    monkeypatch.setenv("QUODEQ_CANCEL_GRACE_S", "0.05")
    _write_pid(tmp_path)
    proc = _StubbornProcess()
    mixin = FsEvaluationMixin()
    mixin._jobs = _manager(proc)
    snapshot = JobSnapshot(job_id="ext-run", status="running", output_project="proj", output_run_id="run")
    alive_when_scored: list[bool] = []

    with patch.object(FsEvaluationMixin, "get_evaluation_status", return_value=snapshot), \
         patch(_WAIT_TERMINAL), \
         patch(_SCORE, side_effect=lambda *_a: alive_when_scored.append(proc.pid_alive(0))):
        assert mixin.cancel_evaluation("ext-run", reports_dir=str(tmp_path), wait_for_exit=True) is True

    assert alive_when_scored == [False]
    assert proc.threads == []
