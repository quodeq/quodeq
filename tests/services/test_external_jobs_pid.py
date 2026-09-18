"""External-run PID resolution, cancel without a pid file, and path-segment validation."""
from __future__ import annotations

import os

from quodeq.services._external_jobs import is_safe_run_segment, resolve_external_pid


# ---------------------------------------------------------------------------
# PID resolution
# ---------------------------------------------------------------------------

def test_resolve_external_pid_returns_none_without_pid_file(tmp_path):
    from quodeq.services._external_jobs import resolve_external_pid

    (tmp_path / "proj" / "run").mkdir(parents=True)
    assert resolve_external_pid(tmp_path / "proj", "run") is None


def test_resolve_external_pid_returns_pid_when_alive(tmp_path):
    from quodeq.services._external_jobs import resolve_external_pid

    run_dir = tmp_path / "proj" / "run"
    run_dir.mkdir(parents=True)
    (run_dir / ".pid").write_text(str(os.getpid()))
    assert resolve_external_pid(tmp_path / "proj", "run") == os.getpid()


def test_resolve_external_pid_returns_none_when_process_dead(tmp_path):
    from quodeq.services._external_jobs import resolve_external_pid

    run_dir = tmp_path / "proj" / "run"
    run_dir.mkdir(parents=True)
    # Use a very high PID that's almost certainly not in use
    (run_dir / ".pid").write_text("999999")
    assert resolve_external_pid(tmp_path / "proj", "run") is None


def test_resolve_external_pid_returns_none_for_corrupt_pid_file(tmp_path):
    from quodeq.services._external_jobs import resolve_external_pid

    run_dir = tmp_path / "proj" / "run"
    run_dir.mkdir(parents=True)
    (run_dir / ".pid").write_text("not-a-number")
    assert resolve_external_pid(tmp_path / "proj", "run") is None


# ---------------------------------------------------------------------------
# cancel_external_run
# ---------------------------------------------------------------------------

def test_cancel_external_run_returns_false_without_pid_file(tmp_path):
    from quodeq.services._external_jobs import cancel_external_run

    (tmp_path / "proj" / "run").mkdir(parents=True)
    assert cancel_external_run("proj", "run", tmp_path) is False


# ---------------------------------------------------------------------------
# Path-segment validation for externally-supplied run/project ids
# ---------------------------------------------------------------------------


class TestIsSafeRunSegment:
    def test_accepts_uuid(self):
        assert is_safe_run_segment("d5b8a421-8c9f-4e11-9b7a-1f2e3d4c5b6a")

    def test_accepts_dotted_and_underscored_names(self):
        assert is_safe_run_segment("run_1.backup-2")

    def test_rejects_dot_and_dotdot(self):
        assert not is_safe_run_segment(".")
        assert not is_safe_run_segment("..")

    def test_rejects_empty(self):
        assert not is_safe_run_segment("")

    def test_rejects_separators(self):
        assert not is_safe_run_segment("a/b")
        assert not is_safe_run_segment("a\\b")
        assert not is_safe_run_segment("../etc")

    def test_rejects_other_charset(self):
        assert not is_safe_run_segment("run id")
        assert not is_safe_run_segment("run\x00id")


class TestResolveExternalPidValidation:
    def test_traversal_run_id_returns_none(self, tmp_path):
        # A '..' run_id would otherwise resolve to reports_root/<proj>/../.pid
        (tmp_path / ".pid").write_text("12345")
        assert resolve_external_pid(tmp_path / "proj", "..") is None

    def test_traversal_project_uuid_returns_none(self, tmp_path):
        assert resolve_external_pid(tmp_path / "..", "run") is None


class TestCancelExternalValidation:
    def test_cancel_job_rejects_traversal_ext_id(self, tmp_path):
        from quodeq.services.jobs import JobManager

        (tmp_path / ".pid").write_text("12345")
        assert JobManager().cancel_job("ext-..", reports_root=tmp_path) is False
