"""Tests for quodeq.services._run_dimensions."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.services._run_dimensions import (
    configured_dimensions,
    current_standard_dimensions,
)
from quodeq.services.ports import RunInfo


def _write(path: Path, name: str, data: dict) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / name).write_text(json.dumps(data), encoding="utf-8")


def _make_run(reports_root: Path, project: str, run_id: str, dims: list[str]) -> None:
    run_dir = reports_root / project / run_id
    _write(
        run_dir,
        "dimensions.json",
        {"schema_version": 1, "dimensions": {d: {"state": "done"} for d in dims}},
    )


def _info(run_id: str, status: str = "complete") -> RunInfo:
    return RunInfo(run_id=run_id, date_iso="2026-07-01", date_label="d", status=status)


def test_reads_dimensions_json_keys(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write(
        run_dir,
        "dimensions.json",
        {
            "schema_version": 1,
            "dimensions": {
                "security": {"state": "done"},
                "performance": {"state": "done"},
            },
        },
    )
    assert configured_dimensions(run_dir) == {"security", "performance"}


def test_prefers_dimensions_json_over_status(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write(
        run_dir,
        "dimensions.json",
        {"schema_version": 1, "dimensions": {"security": {"state": "done"}}},
    )
    _write(run_dir, "status.json", {"dimensions": ["security", "reliability"]})
    # dimensions.json wins when present and non-empty.
    assert configured_dimensions(run_dir) == {"security"}


def test_falls_back_to_status_json(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    # No dimensions.json — status.json list is the fallback signal.
    _write(run_dir, "status.json", {"dimensions": ["security", "usability"]})
    assert configured_dimensions(run_dir) == {"security", "usability"}


def test_falls_back_when_dimensions_json_empty(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write(run_dir, "dimensions.json", {"schema_version": 1, "dimensions": {}})
    _write(run_dir, "status.json", {"dimensions": ["security"]})
    assert configured_dimensions(run_dir) == {"security"}


def test_empty_set_when_absent(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assert configured_dimensions(run_dir) == set()


def test_empty_set_when_status_dimensions_not_a_list(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write(run_dir, "status.json", {"dimensions": "security"})
    assert configured_dimensions(run_dir) == set()


# ---------------------------------------------------------------------------
# current_standard_dimensions — union over the last N eligible runs
# ---------------------------------------------------------------------------

_FULL = ["A", "B", "C", "D", "E", "F"]


def test_current_standard_dimensions_unions_recent_eligible_runs(tmp_path: Path) -> None:
    """Latest eligible run is a subset re-run ({A} only), but prior eligible
    runs configured the full set — the union must recover the full set."""
    reports_root = tmp_path / "evaluations"
    project = "proj"
    # newest-first: subset re-run, then full-set runs.
    _make_run(reports_root, project, "r0", ["A"])  # subset re-run
    _make_run(reports_root, project, "r1", _FULL)
    _make_run(reports_root, project, "r2", ["A"])  # another subset re-run
    _make_run(reports_root, project, "r3", _FULL)
    run_infos = [_info("r0"), _info("r1"), _info("r2"), _info("r3")]

    result = current_standard_dimensions(reports_root, project, run_infos)
    assert result == set(_FULL), f"subset re-run must not collapse standard, got {sorted(result)}"


def test_current_standard_dimensions_drops_retired_dim(tmp_path: Path) -> None:
    """A dimension configured only in a run older than the window is excluded."""
    reports_root = tmp_path / "evaluations"
    project = "proj"
    # 5 recent runs in the window configure {A,B}; the 6th (oldest) had C.
    for i in range(5):
        _make_run(reports_root, project, f"r{i}", ["A", "B"])
    _make_run(reports_root, project, "r5", ["A", "B", "C"])  # outside window of 5
    run_infos = [_info(f"r{i}") for i in range(6)]

    result = current_standard_dimensions(reports_root, project, run_infos, window=5)
    assert result == {"A", "B"}, f"retired C should drop out, got {sorted(result)}"


def test_current_standard_dimensions_excludes_in_progress(tmp_path: Path) -> None:
    """An in_progress latest run is skipped for eligibility. With window=1, the
    standard comes from the first ELIGIBLE run, not the in_progress one."""
    reports_root = tmp_path / "evaluations"
    project = "proj"
    # newest-first: in_progress run configures {A,B,C}; latest complete is {A,B}.
    _make_run(reports_root, project, "live", ["A", "B", "C"])
    _make_run(reports_root, project, "done", ["A", "B"])
    run_infos = [_info("live", status="in_progress"), _info("done", status="complete")]

    # window=1 makes the eligible filter observable: without it, "live" (in_progress)
    # would seed C; with it, only "done" counts.
    result = current_standard_dimensions(reports_root, project, run_infos, window=1)
    assert result == {"A", "B"}, f"in_progress run must be skipped, got {sorted(result)}"


def test_current_standard_dimensions_fails_open_when_all_unreadable(tmp_path: Path) -> None:
    """No config files anywhere -> empty set (fail-open signal)."""
    reports_root = tmp_path / "evaluations"
    project = "proj"
    (reports_root / project / "r0").mkdir(parents=True)
    run_infos = [_info("r0")]
    assert current_standard_dimensions(reports_root, project, run_infos) == set()


def test_current_standard_dimensions_empty_when_no_eligible_runs(tmp_path: Path) -> None:
    """All runs are in_progress/failed -> no eligible runs -> empty set."""
    reports_root = tmp_path / "evaluations"
    project = "proj"
    _make_run(reports_root, project, "r0", _FULL)
    _make_run(reports_root, project, "r1", _FULL)
    run_infos = [_info("r0", status="in_progress"), _info("r1", status="failed")]
    assert current_standard_dimensions(reports_root, project, run_infos) == set()


def test_current_standard_dimensions_rejects_traversal_segments(tmp_path: Path) -> None:
    """A project/run_id with path-traversal is skipped (defense-in-depth, fail-open)."""
    reports_root = tmp_path / "evaluations"
    # A traversal project name must not build a path outside reports_root; the
    # run is skipped and the result is the fail-open empty set.
    assert current_standard_dimensions(reports_root, "../../etc", [_info("r0")]) == set()
    # A traversal run_id is likewise skipped, so a well-formed sibling still counts.
    _make_run(reports_root, "proj", "good", _FULL)
    run_infos = [_info("../evil"), _info("good")]
    assert current_standard_dimensions(reports_root, "proj", run_infos) == set(_FULL)
