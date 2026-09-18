"""Tests for the findings dismiss/restore API endpoints."""
from tests.api._routes_findings_fixtures import app, client  # noqa: F401 -- pytest fixtures


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
        from quodeq.data.events.writer import EventLogWriter
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
        from quodeq.data.events.writer import EventLogWriter
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
        # The delta no longer carries a server-computed rollup — the client
        # derives the Overview accumulated dimension grades from ``scores``.
        assert delta["accumulated"] is None

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
        from quodeq.data.events.writer import EventLogWriter
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
        assert delta["accumulated"] is None

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
