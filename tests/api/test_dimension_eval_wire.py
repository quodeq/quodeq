"""Route-level exact-equality characterization: GET .../dimensions/<dim>/eval.

The dimension-eval wire shaping (``to_camel_dict``, the waiting/202 body)
moved from ``services/fs_reports.py`` to the routes, so this pins the exact
JSON body and status code for ``get_dimension_eval``'s four return shapes --
a JSONL partial with progress, a markdown dimension, a stored JSON eval, and
a pending dimension -- on both the local project route and its
``/api/shared`` mirror. The refactor that moves the shaping must not change
a byte on the wire.

Each test patches ``quodeq.services.fs_reports.resolve_dimension_eval``, the
seam ``get_dimension_eval`` calls after its path-traversal guard: this only
changes how ``get_dimension_eval``'s *return value* is shaped by its
callers, not how ``resolve_dimension_eval`` produces that value, so real
evidence/markdown/JSONL file fixtures are out of scope here (already
characterized by ``tests/services/test_violations*.py``).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from flask import Flask

from quodeq.api.routes_project_data import register_project_data_routes
from quodeq.core.types import Finding, ProgressInfo, ViolationResponse
from quodeq.services.filesystem import FilesystemActionProvider
from tests.api._routes_shared_read_fixtures import app, client  # noqa: F401 -- pytest fixtures

_JSONL_RESPONSE = ViolationResponse(
    dimension="maintainability", run_id="run1", project="proj",
    violations=[Finding(
        practice_id="P1", verdict="violation", file="a.py", line=10,
        title="Bad thing", reason="explanation", severity="major",
    )],
    compliance=[],
    partial=True,
    progress=ProgressInfo(files_read=3, violation_count=1, compliance_count=0),
)

_JSONL_BODY = {
    "dimension": "maintainability", "runId": "run1", "project": "proj",
    "violations": [{
        "practiceId": "P1", "verdict": "violation", "file": "a.py", "line": 10,
        "title": "Bad thing", "reason": "explanation", "severity": "major",
        "reqRefs": [], "confidence": 100, "provenanceDowngrade": False,
        "carriedForward": False,
    }],
    "compliance": [], "partial": True,
    "progress": {"filesRead": 3, "violationCount": 1, "complianceCount": 0},
    "schemaVersion": 1,
}

_MARKDOWN_BODY = {
    "dimension": "maintainability", "runId": "run1", "project": "proj",
    "principleGrades": [{"principle": "Overall", "score": "7.0/10", "grade": "Good", "isOverall": True}],
    "principles": [],
    "priorityRemediation": {"critical": [], "major": [], "minor": []},
    "rawContent": "# Maintainability Evaluation\n\n**Overall Score**: 7.0/10\n",
}

_JSON_EVAL_BODY = {
    "dimension": "maintainability", "runId": "run1", "project": "proj",
    "overallScore": "7.0/10", "overallGrade": "Good",
    "principles": [], "violations": [], "compliance": [],
}


def _resolve_patch(return_value):
    return patch("quodeq.services.fs_reports.resolve_dimension_eval", return_value=return_value)


@pytest.fixture
def project_client(tmp_path):
    reports = tmp_path / "reports"
    (reports / "proj" / "run1").mkdir(parents=True)
    flask_app = Flask(__name__)
    register_project_data_routes(flask_app, FilesystemActionProvider())
    flask_app.config["TESTING"] = True
    # reports_dir() is read at request time (routes_common.reports_dir), so
    # the patch must stay active for the whole test, not just registration.
    with patch("quodeq.api.routes_project_data.reports_dir", return_value=str(reports)):
        with flask_app.test_client() as c:
            yield c


class TestProjectRouteDimensionEval:
    """GET /api/projects/<project>/runs/<run_id>/dimensions/<dimension>/eval."""

    _URL = "/api/projects/proj/runs/run1/dimensions/maintainability/eval"

    def test_jsonl_partial_with_progress(self, project_client):
        with _resolve_patch(_JSONL_RESPONSE):
            resp = project_client.get(self._URL)
        assert resp.status_code == 200
        assert resp.get_json() == _JSONL_BODY

    def test_markdown(self, project_client):
        with _resolve_patch(_MARKDOWN_BODY):
            resp = project_client.get(self._URL)
        assert resp.status_code == 200
        assert resp.get_json() == _MARKDOWN_BODY

    def test_stored_json_eval(self, project_client):
        with _resolve_patch(_JSON_EVAL_BODY):
            resp = project_client.get(self._URL)
        assert resp.status_code == 200
        assert resp.get_json() == _JSON_EVAL_BODY

    def test_pending(self, project_client):
        with _resolve_patch(None):
            resp = project_client.get(self._URL)
        assert resp.status_code == 202
        assert resp.get_json() == {
            "waiting": True, "project": "proj", "runId": "run1", "dimension": "maintainability",
        }


class TestSharedMirrorDimensionEval:
    """GET /api/shared/projects/<project>/dimensions/<dim>/eval?run=<run_id>."""

    _URL = "/api/shared/projects/proj-a/dimensions/maintainability/eval?run=run-1"

    def test_jsonl_partial_with_progress(self, client, shared_clone_fixture):
        with _resolve_patch(_JSONL_RESPONSE):
            resp = client.get(self._URL)
        assert resp.status_code == 200
        assert resp.get_json() == _JSONL_BODY

    def test_markdown(self, client, shared_clone_fixture):
        with _resolve_patch(_MARKDOWN_BODY):
            resp = client.get(self._URL)
        assert resp.status_code == 200
        assert resp.get_json() == _MARKDOWN_BODY

    def test_stored_json_eval(self, client, shared_clone_fixture):
        with _resolve_patch(_JSON_EVAL_BODY):
            resp = client.get(self._URL)
        assert resp.status_code == 200
        assert resp.get_json() == _JSON_EVAL_BODY

    def test_pending(self, client, shared_clone_fixture):
        with _resolve_patch(None):
            resp = client.get(self._URL)
        assert resp.status_code == 202
        assert resp.get_json() == {
            "waiting": True, "project": "proj-a", "runId": "run-1", "dimension": "maintainability",
        }
