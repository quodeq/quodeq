"""Tests for the findings dismiss/restore API endpoints."""
import json
from pathlib import Path

import pytest
from flask import Flask

from quodeq.api.routes_findings import register_findings_routes


@pytest.fixture()
def app(tmp_path):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["EVALUATIONS_DIR"] = str(tmp_path)
    register_findings_routes(app)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


class TestDismissEndpoint:
    def test_dismiss_returns_200_with_scores_envelope(self, client, tmp_path):
        """Dismiss returns ``{"scores": null}`` when no run_id is supplied.

        The endpoint always returns 200 + JSON now; UI applies the rescored
        payload (when present) directly from the response, instead of
        subscribing to an SSE stream and hoping ``scores.updated`` arrives.
        """
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        resp = client.post("/api/findings/dismiss", json={
            "project": "my-project",
            "req": "M-MOD-4", "file": "foo.js", "line": 4,
            "dimension": "maintainability", "severity": "minor",
            "reason": "False positive",
        })
        assert resp.status_code == 200
        assert resp.get_json() == {"scores": None}

    def test_dismiss_appends_to_actions_log(self, client, tmp_path):
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        client.post("/api/findings/dismiss", json={
            "project": "my-project",
            "req": "M-MOD-4", "file": "foo.js", "line": 4,
            "dimension": "maintainability", "severity": "minor",
            "reason": "False positive",
        })
        log = project_dir / "actions.jsonl"
        assert log.exists()
        text = log.read_text()
        assert "FINDING_DISMISSED" in text
        assert "M-MOD-4" in text

    def test_dismiss_missing_fields_returns_400(self, client):
        resp = client.post("/api/findings/dismiss", json={"project": "x"})
        assert resp.status_code == 400

    def test_dismiss_with_run_id_returns_rescored_payload(self, client, tmp_path):
        """When the client supplies ``run_id``, the dismiss response carries
        the rescored ``/scores`` payload for that run. The UI applies it
        synchronously to the principle / explorer state — no SSE roundtrip
        required.
        """
        from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
        from quodeq.core.events.writer import EventLogWriter
        from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository

        run_dir = tmp_path / "my-project" / "run-1"
        run_dir.mkdir(parents=True)
        EventLogWriter(run_dir / "events.jsonl").emit(JudgmentCreatedEvent(payload=JudgmentPayload(
            practice_id="Integrity", verdict="violation", dimension="security",
            file="a.py", line=10, reason="r", req="R1", severity="critical",
        )))
        # Project so SQL has the row, dismiss applies cleanly.
        SqliteFindingsRepository(run_dir).list_by_dimension("security")

        resp = client.post("/api/findings/dismiss", json={
            "project": "my-project",
            "req": "R1", "file": "a.py", "line": 10,
            "dimension": "security", "severity": "critical",
            "run_id": "run-1",
        })
        assert resp.status_code == 200
        body = resp.get_json()
        assert "scores" in body
        assert body["scores"] is not None, (
            f"Expected rescored payload in response, got {body!r}. The UI "
            f"depends on this to update the principle-detail-page score "
            f"without a separate GET."
        )
        # Payload shape mirrors GET /api/projects/<p>/scores/<run>.
        assert "dimensions" in body["scores"]
        assert "summary" in body["scores"]


class TestRestoreEndpoint:
    def test_restore_returns_200_with_scores_envelope(self, client, tmp_path):
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        client.post("/api/findings/dismiss", json={
            "project": "my-project",
            "req": "M-MOD-4", "file": "foo.js", "line": 4,
            "dimension": "maintainability", "severity": "minor",
        })
        resp = client.post("/api/findings/restore", json={
            "project": "my-project",
            "req": "M-MOD-4", "file": "foo.js", "line": 4,
        })
        assert resp.status_code == 200
        assert resp.get_json() == {"scores": None}

    def test_restore_appends_undismiss_event(self, client, tmp_path):
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        client.post("/api/findings/dismiss", json={
            "project": "my-project",
            "req": "M-MOD-4", "file": "foo.js", "line": 4,
            "dimension": "maintainability", "severity": "minor",
        })
        client.post("/api/findings/restore", json={
            "project": "my-project",
            "req": "M-MOD-4", "file": "foo.js", "line": 4,
        })
        text = (project_dir / "actions.jsonl").read_text()
        assert "FINDING_DISMISSED" in text
        assert "FINDING_UNDISMISSED" in text
        assert not (project_dir / "dismissed.json").exists()


class TestListDismissedEndpoint:
    def test_list_returns_empty_without_sql_projection(self, client, tmp_path):
        # Without projection, load_dismissed returns [] since no evaluation.db rows exist.
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        client.post("/api/findings/dismiss", json={
            "project": "my-project",
            "req": "M-MOD-4", "file": "foo.js", "line": 4,
            "dimension": "maintainability", "severity": "minor",
        })
        resp = client.get("/api/findings/dismissed?project=my-project")
        assert resp.status_code == 200
        # Action log was written but no SQL projection happened, so list is empty.
        assert resp.get_json() == []

    def test_list_empty_project(self, client):
        resp = client.get("/api/findings/dismissed?project=nonexistent")
        assert resp.status_code == 200
        assert resp.get_json() == []
