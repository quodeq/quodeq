"""Tests for the /api/rescore endpoint."""
import json
import os
from unittest.mock import patch, MagicMock

import pytest

from quodeq.api.app import create_app

_TEST_RUN_ID = "run-1"
_TEST_DATE_LABEL = "Apr 2"


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
@patch("quodeq.api.routes_rescore.read_run_data")
@patch("quodeq.api.routes_rescore.list_runs")
@patch("quodeq.api.routes_rescore.load_dismissed_keys")
@patch("quodeq.api.routes_rescore.rescore_dimensions")
def test_rescore_returns_rescored_data(mock_rescore, mock_dismissed, mock_list_runs, mock_read_run, _mock_eval, client):
    mock_list_runs.return_value = [MagicMock(run_id=_TEST_RUN_ID, date_iso="2026-04-02", date_label=_TEST_DATE_LABEL)]
    mock_read_run.return_value = []
    mock_dismissed.return_value = set()
    mock_rescore.return_value = {"dimensions": [], "summary": {"dimensionsCount": 0, "overallGrade": None}}

    resp = client.get("/api/rescore?project=test-project")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "dimensions" in data
    assert "summary" in data


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_rescore_rejects_project_symlinked_outside_the_evaluations_root(tmp_path, client):
    """A project name that is a symlink out of the root is refused.

    The segment check alone passed this: "escape" holds no dots or
    separators. Only containment on the *joined* path catches it.
    """
    eval_root = tmp_path / "evaluations"
    eval_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (eval_root / "escape").symlink_to(outside)

    with patch("quodeq.api.routes_rescore._eval_dir_from_app", return_value=str(eval_root)):
        resp = client.get("/api/rescore?project=escape")

    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_PARAM"
