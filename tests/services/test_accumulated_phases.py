"""Unit tests for the two phase helpers behind ``_build_accumulated_for_runs``.

``_load_run_dimensions`` owns the cache wiring plus the run walk;
``_suppress_run_dimensions`` owns the dismissed/deleted filtering.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.data.fs.report_parser.runs import RunInfo
from quodeq.services.accumulated import (
    AccumulatedCacheConfig,
    _load_run_dimensions,
    _suppress_run_dimensions,
)

from tests.services._accumulated_fixtures import _dim, _setup_project


def _run_infos(*run_ids: str) -> list[RunInfo]:
    return [RunInfo(run_id=r, date_iso=None, date_label=r) for r in run_ids]


def test_load_run_dimensions_returns_latest_prev_and_prev_run(tmp_path: Path) -> None:
    """Two runs, newest first: latest wins per dimension, the older run
    supplies the previous occurrence and the previous run's snapshot."""
    reports_root = _setup_project(tmp_path, "proj", [
        ("run-2", [_dim("security", "8.0", "A"), _dim("performance", "6.0", "C")]),
        ("run-1", [_dim("security", "5.0", "D"), _dim("performance", "4.0", "F")]),
    ])

    latest, prev_occurrence, prev_run_latest = _load_run_dimensions(
        reports_root, "proj", _run_infos("run-2", "run-1"), None,
    )

    assert sorted(latest) == ["performance", "security"]
    assert latest["security"].overall_score == "8.0"
    assert prev_occurrence["security"].overall_score == "5.0"
    assert sorted(d.dimension for d in prev_run_latest) == ["performance", "security"]


def test_load_run_dimensions_honours_isolated_cache_config(tmp_path: Path) -> None:
    """A caller-supplied cache_config isolates the walk from the process cache."""
    reports_root = _setup_project(tmp_path, "proj", [
        ("run-1", [_dim("security", "8.0", "A")]),
    ])
    cache_config = AccumulatedCacheConfig()

    latest, _, _ = _load_run_dimensions(
        reports_root, "proj", _run_infos("run-1"), cache_config,
    )

    assert list(latest) == ["security"]
    # The isolated config backs the walk too, so the shared process cache
    # stays untouched while the per-call one fills.
    assert cache_config.cache


def _violation(req: str, file: str, line: int) -> dict[str, object]:
    return {"req": req, "file": file, "line": line, "severity": "major", "description": req}


def test_suppress_run_dimensions_drops_dismissed_violations(tmp_path: Path) -> None:
    """A dismissed finding is filtered out; the untouched dimension survives."""
    project_dir = tmp_path / "evaluations" / "proj"
    project_dir.mkdir(parents=True)
    (project_dir / "actions.jsonl").write_text(
        json.dumps({
            "event_id": "0f9d1e5e-3d1b-4c9a-9f5a-000000000001",
            "timestamp": "2026-01-02T00:00:00Z",
            "event_type": "FINDING_DISMISSED",
            "payload": {"req": "R1", "file": "a.py", "line": 10, "reason": "noise"},
        }) + "\n",
        encoding="utf-8",
    )
    latest = {
        "security": _dim("security", violations=[_violation("R1", "a.py", 10)]),
        "performance": _dim("performance", violations=[_violation("R2", "b.py", 3)]),
    }

    kept = _suppress_run_dimensions(latest, project_dir)

    assert [d.dimension for d in kept] == ["security", "performance"]
    assert kept[0].violations == []
    assert [v.req for v in kept[1].violations] == ["R2"]


def test_suppress_run_dimensions_passes_through_without_suppressions(tmp_path: Path) -> None:
    """With no dismissed/deleted state the mapping's values come back as a list."""
    project_dir = tmp_path / "evaluations" / "proj"
    project_dir.mkdir(parents=True)

    kept = _suppress_run_dimensions({"security": _dim("security", "9.0", "A")}, project_dir)

    assert [d.dimension for d in kept] == ["security"]
    assert kept[0].overall_score == "9.0"
