"""The dashboard payload carries a since-baseline summary per dimension."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from quodeq.core.types import DimensionSummary
from quodeq.services.dashboard import build_dashboard
from tests.services._dashboard_fixtures import _dim, _make_run

_PROJECT = "proj"
_PREV, _CURR = "r-prev", "r-curr"
_DIM = "maintainability"


def _seed(root: Path, run_id: str, started_at: str, violations: list[dict]) -> None:
    run_dir = root / _PROJECT / run_id
    (run_dir / "evaluation").mkdir(parents=True)
    (run_dir / "evaluation" / f"{_DIM}.json").write_text(json.dumps({
        "dimension": _DIM, "principles": [], "violations": violations, "compliance": []}),
        encoding="utf-8")
    (run_dir / "status.json").write_text(json.dumps({"state": "done", "started_at": started_at}),
                                          encoding="utf-8")


def _v(req: str, file: str) -> dict:
    return {"req": req, "file": file, "line": 1, "snippet": f"{req} {file}", "severity": "minor"}


def test_dashboard_carries_since_baseline_summary(tmp_path: Path) -> None:
    _seed(tmp_path, _PREV, "2026-09-20T00:00:00Z", [_v("M-REU-1", "b.py")])
    _seed(tmp_path, _CURR, "2026-09-26T00:00:00Z", [_v("M-ANA-9", "a.py"), _v("M-TST-5", "b.py")])
    runs = [_make_run(_CURR, "2026-09-26"), _make_run(_PREV, "2026-09-20")]
    summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)
    with (
        patch("quodeq.services.dashboard.list_runs", return_value=runs),
        patch("quodeq.services.dashboard.read_run_data", return_value=[_dim(_DIM, "B", "7.0")]),
        patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
    ):
        result = build_dashboard(str(tmp_path), _PROJECT, _CURR)

    since = result["sinceBaseline"][_DIM]
    assert since["againstRunId"] == _PREV
    assert since["types"] == {"closed": ["M-REU-1"], "opened": ["M-ANA-9", "M-TST-5"]}
    assert since["sinceBaseline"] == {"scope": "all", "changedFiles": None,
                                      "counts": {"new": 2, "resolved": 1}}
    assert "new" not in since["sinceBaseline"]


def test_dashboard_without_reports_has_empty_since_baseline(tmp_path: Path) -> None:
    runs = [_make_run("r1", "2026-09-26")]
    summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)
    with (
        patch("quodeq.services.dashboard.list_runs", return_value=runs),
        patch("quodeq.services.dashboard.read_run_data", return_value=[_dim("security", "B", "7.0")]),
        patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
    ):
        result = build_dashboard(str(tmp_path), _PROJECT, "r1")
    assert result["sinceBaseline"] == {}
