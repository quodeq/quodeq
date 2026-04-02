"""Tests for the /api/rescore endpoint."""
import json
from unittest.mock import patch, MagicMock

import pytest

from quodeq.api.app import create_app


@pytest.fixture
def client():
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as c:
        yield c


def test_rescore_requires_project(client):
    resp = client.get("/api/rescore")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "project" in data.get("error", "").lower()


@patch("quodeq.api.routes_rescore._eval_dir_from_app", return_value="/tmp/eval")
@patch("quodeq.api.routes_rescore._reports_dir_from_app", return_value="/tmp/reports")
@patch("quodeq.api.routes_rescore.read_run_data")
@patch("quodeq.api.routes_rescore.list_runs")
@patch("quodeq.api.routes_rescore.load_dismissed_keys")
@patch("quodeq.api.routes_rescore.rescore_dimensions")
def test_rescore_returns_rescored_data(mock_rescore, mock_dismissed, mock_list_runs, mock_read_run, _mock_reports, _mock_eval, client):
    mock_list_runs.return_value = [MagicMock(run_id="run-1", date_iso="2026-04-02", date_label="Apr 2")]
    mock_read_run.return_value = []
    mock_dismissed.return_value = set()
    mock_rescore.return_value = {"dimensions": [], "summary": {"dimensionsCount": 0, "overallGrade": None}}

    resp = client.get("/api/rescore?project=test-project")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "dimensions" in data
    assert "summary" in data
