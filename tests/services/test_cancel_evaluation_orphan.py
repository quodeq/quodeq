"""Cancel must escape the user from a phantom 'running' row.

When the index says ``state=running`` but the underlying process is gone
(SIGTERM has nothing to signal), cancel today returns False and the dashboard
returns 409. The user is stuck. The fix: at cancel time, verify liveness; if
the process is dead, promote the row to ``cancelled(stale_detected)`` so the
UI flips to a terminal state. Findings on disk and the index row are preserved.
"""
from __future__ import annotations

import os
import signal
from pathlib import Path

import pytest

from quodeq.services.filesystem import FilesystemActionProvider
from quodeq.services.run_index import open_index
from quodeq.shared.run_status import RunState, write_status


def _make_run_dir(reports: Path, project: str, run_id: str) -> Path:
    d = reports / project / run_id
    (d / "evidence").mkdir(parents=True)
    (d / "evidence" / "manifest.json").write_text("{}")
    return d


def test_cancel_orphan_no_run_dir_unblocks_user(tmp_path: Path) -> None:
    """The exact production trap: row says running, process gone, run_dir gone.

    Cancel must return True so the dashboard returns 200 and the UI escapes
    the stuck "Evaluation in Progress" panel. Whether the row gets swept
    by ``sync_index``'s orphan sweeper or promoted to cancelled is an
    implementation detail; the contract is "this job is no longer running."
    """
    reports = tmp_path / "reports"
    reports.mkdir()
    db_path = tmp_path / "idx.db"
    db = open_index(db_path)
    try:
        ghost_dir = reports / "ghost-project" / "ghost-run"
        db.execute(
            "INSERT INTO runs (job_id, project_uuid, run_id, run_dir, state, "
            "started_at, updated_at, status_mtime, pid) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "ext-ghost", "ghost-project", "ghost-run", str(ghost_dir),
                "running", "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00", 0, 999999999,
            ),
        )
        db.commit()
    finally:
        db.close()

    provider = FilesystemActionProvider(index_db_path=db_path)
    ok = provider.cancel_evaluation("ext-ghost", reports_dir=str(reports))
    assert ok is True, "cancel must unblock the user when the process is gone"

    # Post-condition: the job is no longer surfaced as running. The row is
    # either gone (swept) or cancelled (promoted) — both unblock the UI.
    snapshot = provider.get_evaluation_status("ext-ghost", reports_dir=str(reports))
    assert snapshot is None or snapshot.status != "running"


def test_cancel_orphan_with_run_dir_preserves_findings(tmp_path: Path) -> None:
    """When the run_dir exists with partial work, cancel-on-orphan must
    preserve evidence and update status.json — not delete anything.

    Realistic scenario: process died but heartbeat is still fresh, so the
    background stale-check (in ``_check_stale_and_promote``) hasn't promoted
    the row yet. The user clicks Cancel; SIGTERM has nothing to signal; the
    fallback must promote the row to ``cancelled(stale_detected)``.
    """
    reports = tmp_path / "reports"
    run = _make_run_dir(reports, "p", "stale-run")
    write_status(
        run, state=RunState.RUNNING, job_id="ext-stale-run",
        started_at="2026-04-20T00:00:00+00:00", dimensions=["security"],
        pid=999999999,
    )
    # Fresh heartbeat — keeps the background stale-check from auto-promoting
    # before our cancel call has a chance to run.
    (run / ".heartbeat").touch()
    # .pid mirrors the dead PID written into status.json so cancel_external_run
    # finds the file and treats the pid-liveness check as authoritative.
    (run / ".pid").write_text("999999999")
    # Sentinel that proves we don't wipe findings on the cancel-orphan path.
    sentinel = run / "evidence" / "security_evidence.jsonl"
    sentinel.write_text('{"finding":"x"}\n')

    db_path = tmp_path / "idx.db"
    provider = FilesystemActionProvider(index_db_path=db_path)
    # Seed the index from disk
    provider.list_evaluations(limit=0, reports_dir=str(reports))

    ok = provider.cancel_evaluation("ext-stale-run", reports_dir=str(reports))
    assert ok is True

    snapshot = provider.get_evaluation_status("ext-stale-run", reports_dir=str(reports))
    assert snapshot is not None
    assert snapshot.status == "cancelled"
    assert sentinel.exists(), "evidence must be preserved on cancel-orphan path"
    assert run.exists(), "run_dir must be preserved (history)"


def test_cancel_terminal_state_unchanged(tmp_path: Path) -> None:
    """Cancel must not touch a row that is already in a terminal state.

    Guards against accidentally rewriting history when the user double-clicks
    Cancel or there's a race between client and server.
    """
    reports = tmp_path / "reports"
    run = _make_run_dir(reports, "p", "done-run")
    write_status(
        run, state=RunState.DONE, job_id="ext-done-run",
        started_at="2026-04-20T00:00:00+00:00", dimensions=[],
    )
    db_path = tmp_path / "idx.db"
    provider = FilesystemActionProvider(index_db_path=db_path)
    provider.list_evaluations(limit=0, reports_dir=str(reports))

    ok = provider.cancel_evaluation("ext-done-run", reports_dir=str(reports))
    assert ok is False, "cancelling a terminal row must be a no-op (returns False)"

    snapshot = provider.get_evaluation_status("ext-done-run", reports_dir=str(reports))
    assert snapshot is not None
    assert snapshot.status == "done", "terminal state must not be rewritten"


def test_cancel_live_pid_unchanged_behavior(tmp_path: Path) -> None:
    """Sanity check: when the PID is genuinely alive, cancel still goes
    through the SIGTERM path (and our promote-on-orphan fallback does NOT
    fire). Uses os.getpid() — a guaranteed live PID."""
    reports = tmp_path / "reports"
    run = _make_run_dir(reports, "p", "live-run")
    write_status(
        run, state=RunState.RUNNING, job_id="ext-live-run",
        started_at="2026-04-20T00:00:00+00:00", dimensions=[],
        pid=os.getpid(),
    )
    # .pid file is what cancel_external_run reads
    (run / ".pid").write_text(str(os.getpid()))

    db_path = tmp_path / "idx.db"
    provider = FilesystemActionProvider(index_db_path=db_path)
    provider.list_evaluations(limit=0, reports_dir=str(reports))

    # We don't want to actually SIGTERM ourselves; intercept the syscalls.
    # cancel_external_run signals the process *group* via os.killpg, so we
    # must intercept that too -- patching only os.kill would let the real
    # SIGTERM through and take down the test runner. We also simulate the
    # SIGTERM being honored so the grace-period poll doesn't burn 30s.
    import quodeq.services._external_jobs as _ext_mod
    import quodeq.services._index_sync as _sync_mod
    original_kill = os.kill
    original_killpg = os.killpg
    original_alive = _sync_mod._is_pid_alive
    sent_signals: list[tuple[int, int]] = []
    pid_killed = False

    def fake_kill(pid: int, sig: int) -> None:
        if sig == 0:
            return original_kill(pid, sig)
        sent_signals.append((pid, sig))

    def fake_killpg(pgid: int, sig: int) -> None:
        nonlocal pid_killed
        sent_signals.append((pgid, sig))
        if sig == signal.SIGTERM:
            pid_killed = True

    def fake_alive(pid: int) -> bool:
        # Once SIGTERM is "sent", report the process as gone so the cancel
        # path exits the grace-period poll immediately.
        if pid_killed:
            return False
        return original_alive(pid)

    _ext_mod.os.kill = fake_kill  # type: ignore[attr-defined]
    _ext_mod.os.killpg = fake_killpg  # type: ignore[attr-defined]
    _sync_mod._is_pid_alive = fake_alive  # type: ignore[attr-defined]
    try:
        ok = provider.cancel_evaluation("ext-live-run", reports_dir=str(reports))
    finally:
        _ext_mod.os.kill = original_kill  # type: ignore[attr-defined]
        _ext_mod.os.killpg = original_killpg  # type: ignore[attr-defined]
        _sync_mod._is_pid_alive = original_alive  # type: ignore[attr-defined]

    assert ok is True
    assert sent_signals, "SIGTERM path must be taken when PID is alive"
    assert any(sig == signal.SIGTERM for _, sig in sent_signals), (
        f"expected SIGTERM to be sent, got: {sent_signals}"
    )
