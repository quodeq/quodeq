"""progress_writer and count_projects write the sync fields into a job slot."""
from __future__ import annotations

from quodeq.core.types.sync_phase import SyncPhase
from quodeq.data.fs.git_progress import ProgressUpdate
from quodeq.services.job_status import JobSlotStatus, phase_durations
from quodeq.services.shared_connect_job import ConnectState
from quodeq.services.sync_progress import SYNC_IDLE_FIELDS, count_projects, progress_writer


class _Slot(JobSlotStatus):
    def __init__(self):
        super().__init__({"state": ConnectState.IDLE, **SYNC_IDLE_FIELDS}, ConnectState.RUNNING)


def test_progress_writer_sets_downloading_and_keeps_last_bytes():
    slot = _Slot()
    write = progress_writer(slot)
    write(ProgressUpdate(10, 1000))
    write(ProgressUpdate(45, None))
    snap = slot.copy()
    assert snap["phase"] is SyncPhase.DOWNLOADING and snap["percent"] == 45 and snap["bytes"] == 1000


def test_progress_writer_follows_git_into_resolving_and_checkout():
    slot = _Slot()
    write = progress_writer(slot)
    write(ProgressUpdate(100, 5000))
    write(ProgressUpdate(30, None, SyncPhase.RESOLVING))
    snap = slot.copy()
    assert snap["phase"] is SyncPhase.RESOLVING and snap["percent"] == 30 and snap["bytes"] == 5000
    write(ProgressUpdate(12, None, SyncPhase.CHECKOUT))
    assert slot.copy()["phase"] is SyncPhase.CHECKOUT


def test_every_phase_change_is_stamped_once():
    ticks = iter([10.0, 20.0, 20.5, 31.0])
    slot = JobSlotStatus({"state": ConnectState.IDLE, **SYNC_IDLE_FIELDS}, ConnectState.RUNNING, clock=lambda: next(ticks))
    assert slot.claim_slot(phase=SyncPhase.CONNECTING)
    write = progress_writer(slot)
    write(ProgressUpdate(10, 1000))
    write(ProgressUpdate(45, None))  # same phase: no new stamp
    write(ProgressUpdate(30, None, SyncPhase.RESOLVING))
    snap = slot.copy()
    assert snap["phase_times"] == [["connecting", 10.0], ["downloading", 20.0], ["resolving", 20.5]]
    assert all(type(phase) is str for phase, _ in snap["phase_times"])  # plain str on the wire, not the enum
    assert phase_durations(snap, finished_at=40.0) == "connecting 10.0s · downloading 0.5s · resolving 19.5s"
    # A new claim starts from an empty record, never the previous job's.
    slot.set(state=ConnectState.IDLE)
    assert slot.claim_slot(phase=SyncPhase.CONNECTING)
    assert slot.copy()["phase_times"] == [["connecting", 31.0]]


def test_a_retried_clone_keeps_every_pass_of_a_phase():
    # A shallow attempt that fails and a full retry both pass through
    # downloading; each pass keeps its own start, so the log books the
    # failed attempt to the right phase instead of to "connecting".
    ticks = iter([0.0, 1.0, 4.0, 5.0, 6.0, 18.0, 19.0])
    slot = JobSlotStatus({"state": ConnectState.IDLE, **SYNC_IDLE_FIELDS}, ConnectState.RUNNING, clock=lambda: next(ticks))
    assert slot.claim_slot(phase=SyncPhase.CONNECTING)
    write = progress_writer(slot)
    write(ProgressUpdate(50, 10))
    write(ProgressUpdate(100, None, SyncPhase.RESOLVING))
    write(ProgressUpdate(20, None))  # the retry downloads again
    write(ProgressUpdate(100, None, SyncPhase.RESOLVING))
    write(ProgressUpdate(10, None, SyncPhase.CHECKOUT))
    slot.set(phase=SyncPhase.READING)
    assert phase_durations(slot.copy(), finished_at=20.0) == (
        "connecting 1.0s · downloading 3.0s · resolving 1.0s · downloading 1.0s · resolving 12.0s · checkout 1.0s · reading 1.0s"
    )


def test_phase_durations_is_empty_without_stamps():
    assert phase_durations({"phase_times": None}) == ""
    assert phase_durations({}) == ""
    assert phase_durations({"phase_times": []}) == ""


def test_count_projects_counts_up_and_reports_reading(tmp_path):
    for i in range(23):
        (tmp_path / f"p{i:02d}").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "file.txt").write_text("x")
    slot = _Slot()
    n = count_projects(tmp_path, slot)
    assert n == 23
    snap = slot.copy()
    assert snap["phase"] is SyncPhase.READING and snap["projects_found"] == 23


def test_count_projects_on_missing_root_is_zero(tmp_path):
    slot = _Slot()
    assert count_projects(tmp_path / "nope", slot) == 0
    assert slot.copy()["projects_found"] == 0
