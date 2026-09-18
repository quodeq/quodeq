"""Tests for the dismissed and verified findings list endpoints."""
import json

from tests.api._routes_findings_fixtures import app, client  # noqa: F401 -- pytest fixtures


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
        from quodeq.data.events.writer import EventLogWriter

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
        from quodeq.data.events.writer import EventLogWriter

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

    def test_verified_list_with_limit_and_offset(self, client, tmp_path):
        """Route handler accepts and passes limit/offset query params."""
        from quodeq.services.verified import verify_finding
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        for i in range(10):
            verify_finding(project_dir, {"req": f"r{i}", "file": "a.py", "line": i, "note": f"n{i}"})

        # Test limit
        resp = client.get("/api/findings/verified?project=my-project&limit=5")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body) == 5

        # Test limit + offset
        resp = client.get("/api/findings/verified?project=my-project&offset=3&limit=4")
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body) == 4

    def test_verified_list_out_of_range_offset(self, client, tmp_path):
        """Out-of-range offset returns empty list."""
        from quodeq.services.verified import verify_finding
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        verify_finding(project_dir, {"req": "r1", "file": "a.py", "line": 3, "note": "n"})

        resp = client.get("/api/findings/verified?project=my-project&offset=100")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_unverify_requires_key_fields(self, client):
        resp = client.post("/api/findings/unverify", json={"project": "p"})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["code"] == "MISSING_PARAM"
