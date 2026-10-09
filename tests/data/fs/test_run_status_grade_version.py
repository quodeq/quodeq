"""status.json records which grade formula version scanned the run."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.analysis.run_lifecycle import LifecycleDeps, RunLifecycleContext
from quodeq.core.run.state import RunState, RunStatus
from quodeq.core.scoring.projector_scoring import GRADE_ALGO_VERSION
from quodeq.data.fs.run_status_store import read_status, write_status
from quodeq.services.run_metadata import read_run_metadata


def test_status_round_trips_the_grade_algorithm_version(tmp_path: Path) -> None:
    status = RunStatus.from_status_dict({"state": "done", "grade_algo_version": 4})
    write_status(tmp_path, status)
    assert (read_status(tmp_path) or {})["grade_algo_version"] == 4
    assert read_run_metadata(tmp_path)["gradeAlgoVersion"] == 4


def test_old_status_without_the_field_reads_none(tmp_path: Path) -> None:
    (tmp_path / "status.json").write_text('{"state": "done"}', encoding="utf-8")
    assert RunStatus.from_status_dict({"state": "done"}).grade_algo_version is None
    assert read_run_metadata(tmp_path)["gradeAlgoVersion"] is None


def test_a_status_without_a_version_does_not_write_the_key(tmp_path: Path) -> None:
    write_status(tmp_path, RunStatus(state=RunState.DONE, job_id="j", started_at="t", dimensions=[]))
    assert "grade_algo_version" not in json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))


def test_a_finished_run_records_the_current_formula_version(tmp_path: Path) -> None:
    class _Stub:
        def start(self) -> None: ...
        def stop(self, *_a: object, **_k: object) -> None: ...

    written: list[RunStatus] = []
    deps = LifecycleDeps(
        write_status=lambda _dir, status: written.append(status),
        heartbeat_factory=lambda _dir: _Stub(), resources_factory=_Stub,
    )
    with RunLifecycleContext(tmp_path, "ext-x", ["security"], deps=deps):
        pass
    assert written[-1].state is RunState.DONE
    assert {s.grade_algo_version for s in written} == {GRADE_ALGO_VERSION}
