"""Tests for the /api/rescore endpoint."""
import json
import os
from unittest.mock import patch, MagicMock

import pytest

from quodeq.api.app import create_app
from quodeq.shared.validation import resolve_child_dir

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


@patch("quodeq.services.rescore_run.read_run_data")
@patch("quodeq.services.rescore_run.list_runs")
@patch("quodeq.services.rescore_run.load_dismissed_keys")
@patch("quodeq.services.rescore_run.rescore_dimensions")
def test_rescore_returns_rescored_data(mock_rescore, mock_dismissed, mock_list_runs, mock_read_run, tmp_path, client):
    # The route resolves both the project and the run against the directory
    # listing, so the evaluations root has to actually contain them. list_runs
    # is mocked to report this run; on disk a reported run always has a
    # directory, and the fixture now matches that.
    (tmp_path / "test-project" / _TEST_RUN_ID).mkdir(parents=True)
    mock_list_runs.return_value = [MagicMock(run_id=_TEST_RUN_ID, date_iso="2026-04-02", date_label=_TEST_DATE_LABEL)]
    mock_read_run.return_value = []
    mock_dismissed.return_value = set()
    mock_rescore.return_value = {"dimensions": [], "summary": {"dimensionsCount": 0, "overallGrade": None}}

    with patch("quodeq.api.routes_rescore._eval_dir_from_app", return_value=str(tmp_path)):
        resp = client.get("/api/rescore?project=test-project")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "dimensions" in data
    assert "summary" in data


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_rescore_rejects_project_symlinked_outside_the_evaluations_root(tmp_path, client):
    """A project name that is a symlink out of the root is refused.

    The segment check alone passed this: "escape" holds no dots or
    separators. Listing-based resolution refuses it because the entry is a
    symlink, not a real directory, so it never matches — hence 404 (no such
    project) rather than the 400 the containment check used to return. The
    security property is the same: the escaped directory is never reached.
    """
    eval_root = tmp_path / "evaluations"
    eval_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (eval_root / "escape").symlink_to(outside)

    with patch("quodeq.api.routes_rescore._eval_dir_from_app", return_value=str(eval_root)):
        resp = client.get("/api/rescore?project=escape")

    assert resp.status_code == 404
    assert resp.get_json()["code"] == "NOT_FOUND"
    # Assert the security property directly, not just the status code: a 404
    # is also what an escaped-but-empty directory would produce, so the status
    # alone does not discriminate between "refused" and "walked out and found
    # nothing". This line fails if the resolver ever starts following links.
    assert resolve_child_dir(eval_root, "escape") is None
