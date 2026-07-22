"""Tests for the findings dismiss/restore API endpoints."""
import json

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
        body = resp.get_json()
        assert body["scores"] is None
        assert "delta" in body

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

    def test_dismiss_with_run_id_returns_delta_envelope(self, client, tmp_path):
        """The dismiss response carries a ``delta`` envelope so the client can
        patch its dashboard/scores caches synchronously. With a run_id, the
        delta describes the dismissed finding and carries the accumulated
        rollup for the Overview.
        """
        from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
        from quodeq.core.events.writer import EventLogWriter
        from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository

        run_dir = tmp_path / "my-project" / "run-1"
        run_dir.mkdir(parents=True)
        (run_dir / "evidence").mkdir()
        (run_dir / "evidence" / "manifest.json").write_text("{}")
        EventLogWriter(run_dir / "events.jsonl").emit(JudgmentCreatedEvent(payload=JudgmentPayload(
            practice_id="Integrity", verdict="violation", dimension="security",
            file="a.py", line=10, reason="r", req="R1", severity="critical",
        )))
        SqliteFindingsRepository(run_dir).list_by_dimension("security")

        resp = client.post("/api/findings/dismiss", json={
            "project": "my-project",
            "req": "R1", "file": "a.py", "line": 10,
            "dimension": "security", "severity": "critical",
            "run_id": "run-1",
        })
        assert resp.status_code == 200
        body = resp.get_json()
        delta = body["delta"]
        assert delta["kind"] == "dismiss"
        assert delta["runId"] == "run-1"
        assert delta["dismissed"] == {"req": "R1", "file": "a.py", "line": 10}
        assert "isLatest" in delta
        assert delta["accumulated"] is not None
        assert "dimensions" in delta["accumulated"]
        assert "summary" in delta["accumulated"]

    def test_dismiss_without_run_id_delta_has_null_accumulated(self, client, tmp_path):
        """Without a run_id, the delta still describes the dismissed finding but
        carries no run anchor: runId is None and accumulated is None.
        """
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        resp = client.post("/api/findings/dismiss", json={
            "project": "my-project",
            "req": "M-MOD-4", "file": "foo.js", "line": 4,
            "dimension": "maintainability", "severity": "minor",
        })
        assert resp.status_code == 200
        delta = resp.get_json()["delta"]
        assert delta["kind"] == "dismiss"
        assert delta["runId"] is None
        assert delta["accumulated"] is None
        assert delta["dismissed"] == {"req": "M-MOD-4", "file": "foo.js", "line": 4}


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
        body = resp.get_json()
        assert body["scores"] is None
        assert "delta" in body

    def test_restore_with_run_id_returns_delta_envelope(self, client, tmp_path):
        """The restore response carries a ``delta`` (kind=restore) with the
        restored finding key + accumulated rollup so the client patches scores
        instantly and invalidates the run-detail violation source.
        """
        from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
        from quodeq.core.events.writer import EventLogWriter
        from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository

        run_dir = tmp_path / "my-project" / "run-1"
        run_dir.mkdir(parents=True)
        (run_dir / "evidence").mkdir()
        (run_dir / "evidence" / "manifest.json").write_text("{}")
        EventLogWriter(run_dir / "events.jsonl").emit(JudgmentCreatedEvent(payload=JudgmentPayload(
            practice_id="Integrity", verdict="violation", dimension="security",
            file="a.py", line=10, reason="r", req="R1", severity="critical",
        )))
        SqliteFindingsRepository(run_dir).list_by_dimension("security")

        client.post("/api/findings/dismiss", json={
            "project": "my-project", "req": "R1", "file": "a.py", "line": 10,
            "dimension": "security", "severity": "critical", "run_id": "run-1",
        })
        resp = client.post("/api/findings/restore", json={
            "project": "my-project", "req": "R1", "file": "a.py", "line": 10,
            "run_id": "run-1",
        })
        assert resp.status_code == 200
        body = resp.get_json()
        assert "scores" in body
        delta = body["delta"]
        assert delta["kind"] == "restore"
        assert delta["runId"] == "run-1"
        assert delta["restored"] == {"req": "R1", "file": "a.py", "line": 10}
        assert "isLatest" in delta
        assert delta["accumulated"] is not None

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


class TestRestoreAllEndpoint:
    def test_restore_all_returns_delta_envelope(self, client, tmp_path):
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        resp = client.post("/api/findings/restore-all", json={
            "project": "my-project", "run_id": "run-1",
        })
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert "restored" in body
        assert "scores" in body
        delta = body["delta"]
        assert delta["kind"] == "restore_all"
        assert delta["runId"] == "run-1"
        assert "isLatest" in delta
        assert "accumulated" in delta

    def test_restore_all_missing_project_returns_400(self, client):
        resp = client.post("/api/findings/restore-all", json={})
        assert resp.status_code == 400


class TestDeleteEndpoint:
    def test_delete_returns_delta_envelope(self, client, tmp_path):
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        resp = client.post("/api/findings/delete", json={
            "project": "my-project",
            "dimension": "security", "principle": "Integrity", "file": "a.py",
            "run_id": "run-1",
        })
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert "swept" in body
        assert "scores" in body
        delta = body["delta"]
        assert delta["kind"] == "delete"
        assert delta["runId"] == "run-1"
        assert delta["deleted"] == {
            "dimension": "security", "principle": "Integrity", "file": "a.py",
        }
        assert "isLatest" in delta
        assert "accumulated" in delta

    def test_delete_missing_fields_returns_400(self, client):
        resp = client.post("/api/findings/delete", json={"project": "x"})
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "MISSING_PARAM"


class TestDeleteAllEndpoint:
    def test_delete_all_returns_delta_envelope(self, client, tmp_path):
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        resp = client.post("/api/findings/delete-all", json={
            "project": "my-project", "run_id": "run-1",
        })
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert "deleted" in body
        assert "scores" in body
        delta = body["delta"]
        assert delta["kind"] == "delete_all"
        assert delta["runId"] == "run-1"
        assert "isLatest" in delta
        assert "accumulated" in delta

    def test_delete_all_missing_project_returns_400(self, client):
        resp = client.post("/api/findings/delete-all", json={})
        assert resp.status_code == 400


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
        body = resp.get_json()
        assert body["scores"] is None
        assert "delta" in body

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
        body = resp.get_json()
        assert body["scores"] is None
        assert "delta" in body

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


class TestVerifiedEndpoints:
    def test_verified_list_and_unverify(self, client, tmp_path):
        from quodeq.services.verified import verify_finding
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        verify_finding(project_dir, {"req": "r1", "file": "a.py", "line": 3, "note": "n"})

        resp = client.get("/api/findings/verified?project=my-project")
        assert resp.status_code == 200
        body = resp.get_json()
        assert [(e["req"], e["file"], e["line"], e["note"]) for e in body] == [("r1", "a.py", 3, "n")]

        resp = client.post("/api/findings/unverify",
                           json={"project": "my-project", "req": "r1", "file": "a.py", "line": 3})
        assert resp.status_code == 200
        assert client.get("/api/findings/verified?project=my-project").get_json() == []

    def test_unverify_requires_key_fields(self, client):
        resp = client.post("/api/findings/unverify", json={"project": "p"})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["code"] == "MISSING_PARAM"


class TestBodyTypeValidation:
    """REL-038/039/040/041: malformed field types must 400 at the API
    boundary instead of crashing in the service layer (a 500)."""

    def test_dismiss_rejects_list_req(self, client, tmp_path):
        (tmp_path / "my-project").mkdir()
        resp = client.post("/api/findings/dismiss", json={
            "project": "my-project", "req": ["M-MOD-4"], "file": "foo.js", "line": 4,
        })
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_dismiss_rejects_string_line(self, client, tmp_path):
        (tmp_path / "my-project").mkdir()
        resp = client.post("/api/findings/dismiss", json={
            "project": "my-project", "req": "M-MOD-4", "file": "foo.js", "line": "4",
        })
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_dismiss_rejects_bool_line(self, client, tmp_path):
        (tmp_path / "my-project").mkdir()
        resp = client.post("/api/findings/dismiss", json={
            "project": "my-project", "req": "M-MOD-4", "file": "foo.js", "line": True,
        })
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_restore_rejects_dict_file(self, client, tmp_path):
        (tmp_path / "my-project").mkdir()
        resp = client.post("/api/findings/restore", json={
            "project": "my-project", "req": "M-MOD-4", "file": {"p": "foo.js"}, "line": 4,
        })
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_delete_rejects_list_dimension(self, client, tmp_path):
        (tmp_path / "my-project").mkdir()
        resp = client.post("/api/findings/delete", json={
            "project": "my-project", "dimension": ["security"],
            "principle": "Integrity", "file": "foo.js",
        })
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_unverify_rejects_int_req(self, client, tmp_path):
        (tmp_path / "my-project").mkdir()
        resp = client.post("/api/findings/unverify", json={
            "project": "my-project", "req": 7, "file": "a.py", "line": 3,
        })
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_missing_fields_still_report_missing_param(self, client):
        # The MISSING_PARAM contract for absent fields is unchanged.
        resp = client.post("/api/findings/dismiss", json={"project": "x"})
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "MISSING_PARAM"
