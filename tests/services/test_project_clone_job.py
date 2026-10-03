from quodeq.core.types.sync_phase import SyncKind, SyncPhase
from quodeq.data.fs.git_progress import ProgressUpdate
from quodeq.services.project_clone_job import (
    CloneHooks, CloneOutcome, CloneState, CloneStartResult, CloneStatus, get_clone_status, is_clone_running, start_clone,
)


def inline(target):
    target()


def test_start_clone_reports_phases_percent_and_the_created_project():
    status = CloneStatus()
    seen = []

    def create(progress, on_phase):
        seen.append(get_clone_status(status)["phase"])
        progress(ProgressUpdate(percent=45, bytes=12_000_000))
        seen.append((get_clone_status(status)["phase"], get_clone_status(status)["percent"]))
        on_phase(SyncPhase.READING)
        seen.append(get_clone_status(status)["phase"])
        return CloneOutcome(True, project_id="p1", project_name="repo", scan_data={"files": 3})
    result = start_clone("https://github.com/o/repo.git", "/tmp/x/repo", hooks=CloneHooks(create, spawn=inline), status=status)
    assert result is CloneStartResult.STARTED
    assert seen == [SyncPhase.CONNECTING, (SyncPhase.DOWNLOADING, 45), SyncPhase.READING]
    snap = get_clone_status(status)
    assert snap["state"] == CloneState.DONE and snap["phase"] == SyncPhase.DONE
    assert snap["project_id"] == "p1" and snap["scan_data"] == {"files": 3} and snap["kind"] == SyncKind.CLONE
    assert snap["finished_at"] is not None and not is_clone_running(status)


def test_failed_outcome_lands_as_error_with_code_and_detail():
    status = CloneStatus()
    start_clone("u", "d", hooks=CloneHooks(lambda p, ph: CloneOutcome(False, error="Repository not found", code="REPO_NOT_FOUND", detail="fatal: not found"), spawn=inline), status=status)
    snap = get_clone_status(status)
    assert snap["state"] == CloneState.ERROR and snap["phase"] == SyncPhase.ERROR
    assert snap["code"] == "REPO_NOT_FOUND" and snap["detail"] == "fatal: not found"


def test_second_start_while_running_is_refused():
    status = CloneStatus()
    assert status.claim("u", "d") is True
    assert start_clone("u2", "d2", hooks=CloneHooks(lambda p, ph: CloneOutcome(True), spawn=inline), status=status) is CloneStartResult.ALREADY_RUNNING


def test_raising_create_becomes_an_error_slot_not_an_exception():
    status = CloneStatus()

    def boom(p, ph):
        raise OSError("disk")
    start_clone("u", "d", hooks=CloneHooks(boom, spawn=inline), status=status)
    assert get_clone_status(status)["code"] == "CLONE_UNEXPECTED"


def test_on_done_runs_after_done_and_cannot_downgrade_it():
    status = CloneStatus()

    def on_done():
        raise RuntimeError("cache")
    start_clone("u", "d", hooks=CloneHooks(lambda p, ph: CloneOutcome(True, project_id="p"), on_done, inline), status=status)
    assert get_clone_status(status)["state"] == CloneState.DONE
