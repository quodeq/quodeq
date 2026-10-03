"""The overview dashboard: same scalars as the full one, no bodies, served from rows.

The selected run comes from its ``run_scalars`` rows, the same rows the
history walk serves, so a warm overview never reads the run's findings.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import quodeq.services.dashboard as dashboard_mod
from quodeq.core.types.dashboard_view import DashboardView
from quodeq.services.dashboard import build_dashboard
from quodeq.services.deleted import delete_finding
from quodeq.services.dismissed import dismiss_finding

RUN = "20260101T000000"


def _write_run(reports: Path, project: str = "proj", run_id: str = RUN) -> Path:
    """A legacy-style on-disk run with two violations in one dimension
    (the same shape tests/services/test_dashboard_build_filtering.py uses)."""
    run_dir = reports / project / run_id
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(parents=True)
    violations = [
        {"principle": "N/A", "req": "N/A", "file": "src/a.py", "line": 73,
         "title": "Arbitrary file read", "severity": "critical", "snippet": "open(p)", "context": "def f():", "reason": "r"},
        {"principle": "Modularity", "req": "M-MOD-1", "file": "src/b.py", "line": 5,
         "title": "Oversized function", "severity": "major", "snippet": "def g():", "context": "...", "reason": "r"},
    ]
    (eval_dir / "maintainability.json").write_text(json.dumps({
        "dimension": "maintainability",
        "overallScore": "6.0/10", "overallGrade": "Fair",
        "principles": [], "violations": violations, "compliance": [],
        "totals": {"violationCount": 2, "complianceCount": 0, "severity": {"critical": 1, "major": 1, "minor": 0}},
    }), encoding="utf-8")
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "manifest.json").write_text('{"language_stats": {}}', encoding="utf-8")
    return run_dir


@pytest.fixture(autouse=True)
def _own_score_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "score-cache.db"))


def _dim(body):
    return body["dimensions"][0]


def test_overview_has_no_bodies_and_same_scalars(tmp_path: Path) -> None:
    _write_run(tmp_path)
    full = build_dashboard(str(tmp_path), "proj", "latest")
    overview = build_dashboard(str(tmp_path), "proj", "latest", view=DashboardView.OVERVIEW)
    f, o = _dim(full), _dim(overview)
    assert "violations" not in o and "compliance" not in o
    assert len(f["violations"]) == 2
    assert o["openTypes"] == 2
    for key in ("overallScore", "overallGrade", "totals", "dismissedCount", "suppressedCount", "dimension"):
        assert o.get(key) == f.get(key), key
    assert overview["trend"] == full["trend"]
    assert overview["selectedRun"] == full["selectedRun"]


def test_dismissal_refreshes_the_overview_rows(tmp_path: Path) -> None:
    _write_run(tmp_path)
    before = _dim(build_dashboard(str(tmp_path), "proj", "latest", view=DashboardView.OVERVIEW))
    dismiss_finding(tmp_path / "proj", {"req": "N/A", "file": "src/a.py", "line": 73})
    after = _dim(build_dashboard(str(tmp_path), "proj", "latest", view=DashboardView.OVERVIEW))
    full = _dim(build_dashboard(str(tmp_path), "proj", "latest"))
    assert before["totals"]["violationCount"] == 2
    assert after["totals"]["violationCount"] == 1 == full["totals"]["violationCount"]
    assert after["dismissedCount"] == 1 == full["dismissedCount"]
    assert after["suppressedCount"] == 1 == full["suppressedCount"]
    assert after["openTypes"] == 1


def test_deletion_counts_as_suppressed_but_not_dismissed(tmp_path: Path) -> None:
    _write_run(tmp_path)
    delete_finding(tmp_path / "proj", {"dimension": "maintainability", "principle": "Modularity", "file": "src/b.py"})
    overview = _dim(build_dashboard(str(tmp_path), "proj", "latest", view=DashboardView.OVERVIEW))
    full = _dim(build_dashboard(str(tmp_path), "proj", "latest"))
    assert "dismissedCount" not in overview and "dismissedCount" not in full
    assert overview["suppressedCount"] == 1 == full["suppressedCount"]
    assert overview["totals"] == full["totals"]


def test_warm_overview_does_not_read_the_findings(tmp_path: Path) -> None:
    _write_run(tmp_path)
    build_dashboard(str(tmp_path), "proj", "latest", view=DashboardView.OVERVIEW)
    with patch.object(dashboard_mod, "read_run_data", wraps=dashboard_mod.read_run_data) as spy:
        build_dashboard(str(tmp_path), "proj", "latest", view=DashboardView.OVERVIEW)
    assert spy.call_count == 0


def test_full_view_still_reparses_each_time(tmp_path: Path) -> None:
    _write_run(tmp_path)
    with patch.object(dashboard_mod, "read_run_data", wraps=dashboard_mod.read_run_data) as spy:
        build_dashboard(str(tmp_path), "proj", "latest")
        build_dashboard(str(tmp_path), "proj", "latest", view=DashboardView.FULL)
    assert spy.call_count == 2


def test_overview_with_no_runs_matches_full(tmp_path: Path) -> None:
    (tmp_path / "proj").mkdir()
    full = build_dashboard(str(tmp_path), "proj", "latest")
    overview = build_dashboard(str(tmp_path), "proj", "latest", view=DashboardView.OVERVIEW)
    assert overview == full
    assert overview["dimensions"] == []


def test_overview_matches_full_for_a_run_without_evals(tmp_path: Path) -> None:
    run_dir = tmp_path / "proj" / RUN
    run_dir.mkdir(parents=True)
    (run_dir / "status.json").write_text(json.dumps({"state": "running", "dateISO": "2026-01-01T00:00:00Z"}))
    full = build_dashboard(str(tmp_path), "proj", "latest")
    overview = build_dashboard(str(tmp_path), "proj", "latest", view=DashboardView.OVERVIEW)
    assert overview["dimensions"] == full["dimensions"] == []
    assert overview["selectedRun"] == full["selectedRun"]
