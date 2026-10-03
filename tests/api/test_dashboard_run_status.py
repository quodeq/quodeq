"""The dashboard payload carries run-list status in the RunState vocabulary.

``availableRuns[].status`` and ``trend[].status`` are "done" for a finished
run and "running" for a live one (the legacy "complete"/"in_progress"
spellings are gone from the wire).
"""
from __future__ import annotations

import json

import pytest

from quodeq.api.app import create_app

_DONE_RUN = "20260101T000000"
_LIVE_RUN = "20260102T000000"


@pytest.fixture(autouse=True)
def _no_auth(monkeypatch):
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)


def _write_run(project_dir, run_id, state):
    run_dir = project_dir / run_id
    (run_dir / "evaluation").mkdir(parents=True)
    (run_dir / "evidence").mkdir()
    (run_dir / "evidence" / "manifest.json").write_text('{"language_stats": {}}', encoding="utf-8")
    (run_dir / "status.json").write_text(json.dumps({"state": state}), encoding="utf-8")
    (run_dir / "evaluation" / "maintainability.json").write_text(json.dumps({
        "dimension": "maintainability", "overallScore": "6.0/10", "overallGrade": "Adequate",
        "principles": [], "violations": [], "compliance": [],
        "totals": {"violationCount": 0, "complianceCount": 0,
                   "severity": {"critical": 0, "major": 0, "minor": 0}},
    }), encoding="utf-8")


def test_dashboard_run_status_is_done_or_running(tmp_path, monkeypatch):
    evals = tmp_path / "evaluations"
    project_dir = evals / "proj"
    _write_run(project_dir, _DONE_RUN, "done")
    _write_run(project_dir, _LIVE_RUN, "running")
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(evals))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "index.db"))
    import quodeq.data.fs.report_parser.runs as runs_mod
    monkeypatch.setattr(
        runs_mod, "resolve_external_pid",
        lambda _project_dir, run_id: 4242 if run_id == _LIVE_RUN else None,
    )

    client = create_app(static_dist=None, api_key=None).test_client()
    resp = client.get(f"/api/projects/proj/dashboard?run={_DONE_RUN}")
    assert resp.status_code == 200
    body = json.loads(resp.get_data())

    available = {r["runId"]: r["status"] for r in body["availableRuns"]}
    trend = {r["runId"]: r["status"] for r in body["trend"]}
    assert available == {_DONE_RUN: "done", _LIVE_RUN: "running"}
    assert trend == {_DONE_RUN: "done", _LIVE_RUN: "running"}
