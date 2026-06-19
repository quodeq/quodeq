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

    def test_dismiss_missing_fields_returns_missing_param_code(self, client):
        resp = client.post("/api/findings/dismiss", json={"project": "x"})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["code"] == "MISSING_PARAM"
        assert "error" in data

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
    def test_restore_missing_fields_returns_missing_param_code(self, client):
        resp = client.post("/api/findings/restore", json={"project": "x"})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["code"] == "MISSING_PARAM"
        assert "error" in data


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
    def test_list_returns_minimal_stub_when_finding_detail_is_unavailable(
        self, client, tmp_path,
    ):
        """With no run dirs, ``load_dismissed`` can't enrich from SQL or JSON
        eval files — but the dismiss still happened, so we must surface a
        minimal stub (req/file/line) so the user can see and restore it.
        """
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        client.post("/api/findings/dismiss", json={
            "project": "my-project",
            "req": "M-MOD-4", "file": "foo.js", "line": 4,
            "dimension": "maintainability", "severity": "minor",
        })
        resp = client.get("/api/findings/dismissed?project=my-project")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body) == 1
        assert body[0]["req"] == "M-MOD-4"
        assert body[0]["file"] == "foo.js"
        assert body[0]["line"] == 4

    def test_dismiss_without_run_id_still_populates_dismissed_list(
        self, client, tmp_path,
    ):
        """Dismiss without ``run_id`` must still update each run's SQL findings.

        The Violations and Map pages navigate into PrincipleDetail without
        knowing the originating run id today, so their dismiss POSTs arrive
        either with no ``run_id`` or with ``run_id='latest'`` (a sentinel,
        not a real directory). Without a fallback projection the action
        lands in actions.jsonl but never reaches each run's evaluation.db,
        so the dismissed-tab list (which reads
        ``WHERE verdict='dismissed'``) stays empty — the user-visible
        symptom that motivated this regression.
        """
        from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
        from quodeq.core.events.writer import EventLogWriter

        run_dir = tmp_path / "my-project" / "run-A"
        run_dir.mkdir(parents=True)
        EventLogWriter(run_dir / "events.jsonl").emit(JudgmentCreatedEvent(payload=JudgmentPayload(
            practice_id="Integrity", verdict="violation", dimension="security",
            file="a.py", line=10, reason="r", req="R1", severity="critical",
        )))

        # No run_id supplied (Violations-page nav path).
        resp = client.post("/api/findings/dismiss", json={
            "project": "my-project",
            "req": "R1", "file": "a.py", "line": 10,
            "dimension": "security", "severity": "critical",
        })
        assert resp.status_code == 200
        assert resp.get_json() == {"scores": None}

        listed = client.get("/api/findings/dismissed?project=my-project").get_json()
        assert len(listed) == 1
        assert listed[0]["req"] == "R1"
        assert listed[0]["file"] == "a.py"
        assert listed[0]["line"] == 10

    def test_dismiss_with_latest_sentinel_still_populates_dismissed_list(
        self, client, tmp_path,
    ):
        """``run_id='latest'`` is a UI sentinel, not a real run dir.

        ``selectedRun`` defaults to ``'latest'`` in the React app; when nav
        paths forget to override it, the dismiss POST carries that string
        verbatim. The backend must treat it the same as a missing run id —
        rescore returns None, the projection-all-runs fallback kicks in.
        """
        from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
        from quodeq.core.events.writer import EventLogWriter

        run_dir = tmp_path / "my-project" / "run-A"
        run_dir.mkdir(parents=True)
        EventLogWriter(run_dir / "events.jsonl").emit(JudgmentCreatedEvent(payload=JudgmentPayload(
            practice_id="Integrity", verdict="violation", dimension="security",
            file="a.py", line=10, reason="r", req="R1", severity="critical",
        )))

        resp = client.post("/api/findings/dismiss", json={
            "project": "my-project",
            "req": "R1", "file": "a.py", "line": 10,
            "dimension": "security", "severity": "critical",
            "run_id": "latest",
        })
        assert resp.status_code == 200
        assert resp.get_json() == {"scores": None}

        listed = client.get("/api/findings/dismissed?project=my-project").get_json()
        assert len(listed) == 1

    def test_list_enriches_legacy_runs_from_json_eval_files(
        self, client, tmp_path,
    ):
        """Legacy runs (no events.jsonl, no SQL findings table) must still
        appear on the Dismissed tab with full detail (principle, severity,
        title, reason, snippet).

        This was the real-world regression: every run in the user's
        installation pre-dated the event-log scoring engine, so projection
        had nothing to write — and ``load_dismissed`` (reading SQL
        ``WHERE verdict='dismissed'``) returned an empty list for every
        dismiss. The fallback path reads from ``evaluation/<dim>.json``
        which exists for every legacy run.
        """
        run_dir = tmp_path / "my-project" / "run-A"
        eval_dir = run_dir / "evaluation"
        eval_dir.mkdir(parents=True)
        (eval_dir / "security.json").write_text(json.dumps({
            "violations": [
                {
                    "req": "S-INT-9",
                    "file": "feature/foo.kt",
                    "line": 173,
                    "principle": "Integrity",
                    "severity": "minor",
                    "title": "API host hardcoded",
                    "reason": "host value comes from a literal constant",
                    "snippet": "val host = \"prod.example.com\"",
                    "context": "...",
                    "req_refs": [{"label": "CWE-20", "url": "https://cwe.mitre.org/20"}],
                },
            ],
        }))

        # No events.jsonl, no evaluation.db — pure legacy layout.
        assert not (run_dir / "events.jsonl").exists()
        assert not (run_dir / "evaluation.db").exists()

        client.post("/api/findings/dismiss", json={
            "project": "my-project",
            "req": "S-INT-9", "file": "feature/foo.kt", "line": 173,
            "dimension": "security", "severity": "minor",
        })

        listed = client.get("/api/findings/dismissed?project=my-project").get_json()
        assert len(listed) == 1
        entry = listed[0]
        assert entry["req"] == "S-INT-9"
        assert entry["file"] == "feature/foo.kt"
        assert entry["line"] == 173
        assert entry["dimension"] == "security"
        assert entry["principle"] == "Integrity"
        assert entry["severity"] == "minor"
        assert entry["title"] == "API host hardcoded"
        assert entry["reason"] == "host value comes from a literal constant"
        assert entry["snippet"] == "val host = \"prod.example.com\""
        assert entry["reqRefs"] == [{"label": "CWE-20", "url": "https://cwe.mitre.org/20"}]

    def test_list_empty_project(self, client):
        resp = client.get("/api/findings/dismissed?project=nonexistent")
        assert resp.status_code == 200
        assert resp.get_json() == []
