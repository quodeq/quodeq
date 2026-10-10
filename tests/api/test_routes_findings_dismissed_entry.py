"""POST /api/findings/dismiss answers with the Dismissed tab's item for the finding."""
from __future__ import annotations

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.data.events.writer import EventLogWriter
from quodeq.data.projection.projector import Projector
from tests.api._routes_findings_fixtures import app, client  # noqa: F401 -- pytest fixtures


def _seed(tmp_path, run_id: str) -> None:
    run_dir = tmp_path / "my-project" / run_id
    run_dir.mkdir(parents=True)
    log = run_dir / "events.jsonl"
    EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="Integrity", verdict="violation", dimension="security",
        file="a.py", line=10, reason="unsafe", req="R1", severity="critical",
        snippet="x = eval(y)",
    )))
    Projector().project(log, run_dir)


def test_dismiss_response_carries_the_listing_item(client, tmp_path):
    _seed(tmp_path, "run-A")

    resp = client.post("/api/findings/dismiss", json={
        "project": "my-project", "req": "R1", "file": "a.py", "line": 10, "run_id": "run-A",
    })

    assert resp.status_code == 200
    entry = resp.get_json()["dismissedEntry"]
    assert entry["req"] == "R1"
    assert entry["dimension"] == "security"
    assert entry["principle"] == "Integrity"
    assert entry["reason"] == "unsafe"
    assert entry["fingerprint"]
    listed = client.get("/api/findings/dismissed?project=my-project").get_json()
    assert listed == [entry]


def test_dismiss_response_item_is_a_stub_when_no_run_holds_the_finding(client, tmp_path):
    (tmp_path / "my-project").mkdir()

    resp = client.post("/api/findings/dismiss", json={
        "project": "my-project", "req": "M-MOD-4", "file": "foo.js", "line": 4,
    })

    entry = resp.get_json()["dismissedEntry"]
    assert (entry["req"], entry["file"], entry["line"]) == ("M-MOD-4", "foo.js", 4)
    assert entry["title"] == ""
