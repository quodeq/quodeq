"""Mutation fallback uses the durable action log, not a local worker thread."""
from __future__ import annotations

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


def test_dismiss_is_projected_by_the_reader(client, tmp_path):
    """A later reader claims only its run's durable action-log delta."""
    from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
    from quodeq.core.events.writer import EventLogWriter
    from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository

    run_dir = tmp_path / "my-project" / "run-A"
    run_dir.mkdir(parents=True)
    EventLogWriter(run_dir / "events.jsonl").emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="Integrity", verdict="violation", dimension="security",
        file="foo.py", line=1, reason="r", req="M-MOD-1", severity="major",
    )))

    response = client.post("/api/findings/dismiss", json={
        "project": "my-project", "req": "M-MOD-1", "file": "foo.py", "line": 1,
    })

    assert response.status_code == 200
    assert not (run_dir / "evaluation.db").exists()

    findings = SqliteFindingsRepository(run_dir).list_all()
    assert len(findings) == 1
    assert findings[0].verdict == "dismissed"
