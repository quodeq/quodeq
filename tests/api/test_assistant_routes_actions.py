"""Assistant action apply/reject routes and the skills catalog."""
import json

from tests.api._assistant_routes_fixtures import (  # noqa: F401 -- app/client are pytest fixtures
    _VALID_STANDARD,
    _repo,
    app,
    client,
)


def test_apply_action_creates_standard(client, app):
    repo = _repo(app)
    repo.create_session(session_id="s1", provider="ollama")
    repo.create_action(action_id="a1", session_id="s1",
                       action_type="create_standard",
                       payload=_VALID_STANDARD, content_hash="h")
    resp = client.post("/api/assistant/actions/a1/apply")
    assert resp.status_code == 200
    assert repo.get_action("a1")["status"] == "applied"
    # standard file written by StandardsService
    import pathlib
    written = pathlib.Path(app.config["STANDARDS_EVALUATORS_DIR"]) / "api-errors.json"
    assert written.exists()
    assert json.loads(written.read_text())["name"] == "API Error Contract"


def test_apply_twice_conflicts(client, app):
    repo = _repo(app)
    repo.create_session(session_id="s1", provider="ollama")
    repo.create_action(action_id="a1", session_id="s1",
                       action_type="create_standard",
                       payload=_VALID_STANDARD, content_hash="h")
    assert client.post("/api/assistant/actions/a1/apply").status_code == 200
    assert client.post("/api/assistant/actions/a1/apply").status_code == 409


def test_reject_action(client, app):
    repo = _repo(app)
    repo.create_session(session_id="s1", provider="ollama")
    repo.create_action(action_id="a1", session_id="s1",
                       action_type="create_standard",
                       payload=_VALID_STANDARD, content_hash="h")
    resp = client.post("/api/assistant/actions/a1/reject")
    assert resp.status_code == 200
    assert repo.get_action("a1")["status"] == "rejected"


def test_apply_unknown_action_404(client):
    assert client.post("/api/assistant/actions/missing/apply").status_code == 404


def test_apply_invalid_payload_400(client, app):
    # A malformed stored draft (missing "principles") must yield a clean 400,
    # not a 500 — import_from_file raises ValueError on validation failure.
    repo = _repo(app)
    repo.create_session(session_id="s1", provider="ollama")
    invalid = {k: v for k, v in _VALID_STANDARD.items() if k != "principles"}
    repo.create_action(action_id="a-bad", session_id="s1",
                       action_type="create_standard",
                       payload=invalid, content_hash="h")
    resp = client.post("/api/assistant/actions/a-bad/apply")
    assert resp.status_code == 400
    assert resp.get_json()["error"]
    assert repo.get_action("a-bad")["status"] == "drafted"


def test_assistant_catalog(client):
    resp = client.get("/api/assistant/skills")
    assert resp.status_code == 200
    body = resp.get_json()
    assert [c["name"] for c in body["commands"]] == ["help", "skills", "actions", "clear"]
    names = {s["name"] for s in body["skills"]}
    assert {"create-standard", "explain-finding", "explain-score"} <= names
    one = next(s for s in body["skills"] if s["name"] == "explain-score")
    assert one["argumentHint"] and isinstance(one["views"], list)
    assert [a["type"] for a in body["actions"]] == ["create_standard", "dismiss_finding", "verify_finding"]
    assert all(a["description"] for a in body["actions"])


def test_reject_after_apply_conflicts(client, app):
    repo = _repo(app)
    repo.create_session(session_id="s1", provider="ollama")
    repo.create_action(action_id="a1", session_id="s1",
                       action_type="create_standard", payload=_VALID_STANDARD,
                       content_hash="h")
    assert client.post("/api/assistant/actions/a1/apply").status_code == 200
    resp = client.post("/api/assistant/actions/a1/reject")
    assert resp.status_code == 409
    sess = repo.get_action("a1")
    assert sess["status"] == "applied"  # apply outcome survives the replay


def test_apply_dismiss_finding_writes_action_log(client, app, tmp_path, monkeypatch):
    evals = tmp_path / "evals"
    (evals / "proj").mkdir(parents=True)
    monkeypatch.setitem(app.config, "EVALUATIONS_DIR", str(evals))
    repo = _repo(app)
    repo.create_session(session_id="s1", provider="ollama")
    repo.create_action(action_id="a1", session_id="s1",
                       action_type="dismiss_finding",
                       payload={"project": "proj", "req": "r1", "file": "a.py",
                                "line": 3, "reason": "false positive: guarded"},
                       content_hash="h")
    resp = client.post("/api/assistant/actions/a1/apply")
    assert resp.status_code == 200
    from quodeq.services.dismissed import dismissed_keys
    assert dismissed_keys(evals / "proj").line_keys() == {("r1", "a.py", 3)}


def test_apply_dismiss_finding_returns_delta_for_run_scoped_session(client, app, tmp_path, monkeypatch):
    # A run-scoped dismiss (runId present, mirroring an assistant session
    # opened against a specific run) must return the same delta shape the
    # manual /api/findings/dismiss route returns, so the UI can patch its
    # caches in place instead of waiting on a lazy refetch.
    evals = tmp_path / "evals"
    run_dir = evals / "proj" / "run1"
    (run_dir / "evaluation").mkdir(parents=True)
    (run_dir / "evaluation" / "security.json").write_text(json.dumps({
        "dimension": "security", "overallScore": 50, "overallGrade": "C",
        "principles": [], "violations": [
            {"principle": "P1", "req": "r1", "file": "a.py", "line": 3,
             "severity": "major", "title": "t", "reason": "r"},
        ],
        "totals": {"violations": 1},
    }))
    monkeypatch.setitem(app.config, "EVALUATIONS_DIR", str(evals))
    repo = _repo(app)
    repo.create_session(session_id="s1", provider="ollama")
    repo.create_action(action_id="a1", session_id="s1",
                       action_type="dismiss_finding",
                       payload={"project": "proj", "req": "r1", "file": "a.py",
                                "line": 3, "reason": "false positive: guarded",
                                "runId": "run1"},
                       content_hash="h")
    resp = client.post("/api/assistant/actions/a1/apply")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["result"]["dismissed"] is True
    delta = body["result"]["delta"]
    assert delta["kind"] == "dismiss"
    assert delta["dismissed"] == {"req": "r1", "file": "a.py", "line": 3}
    # The delta names its own project so the client patches the right cache
    # even if the user switched projects while the apply POST was in flight.
    assert delta["project"] == "proj"
    from quodeq.services.dismissed import dismissed_keys
    assert dismissed_keys(evals / "proj").line_keys() == {("r1", "a.py", 3)}


def test_apply_verify_finding_writes_badge(client, app, tmp_path, monkeypatch):
    evals = tmp_path / "evals"
    (evals / "proj").mkdir(parents=True)
    monkeypatch.setitem(app.config, "EVALUATIONS_DIR", str(evals))
    repo = _repo(app)
    repo.create_session(session_id="s1", provider="ollama")
    repo.create_action(action_id="a1", session_id="s1",
                       action_type="verify_finding",
                       payload={"project": "proj", "req": "r1", "file": "a.py",
                                "line": 3, "note": "real: unsanitized input"},
                       content_hash="h")
    assert client.post("/api/assistant/actions/a1/apply").status_code == 200
    from quodeq.services.verified import verified_entries
    assert [e["note"] for e in verified_entries(evals / "proj")] == ["real: unsanitized input"]


def test_apply_verify_finding_traversal_payload_400(client, app, tmp_path, monkeypatch):
    """A drafted verify_finding whose stored payload has a traversal project must return 400
    and must NOT create any actions.jsonl outside the evaluations root."""
    evals = tmp_path / "evals"
    evals.mkdir(parents=True)
    monkeypatch.setitem(app.config, "EVALUATIONS_DIR", str(evals))
    repo = _repo(app)
    repo.create_session(session_id="s1", provider="ollama")
    repo.create_action(action_id="a-traverse", session_id="s1",
                       action_type="verify_finding",
                       payload={"project": "../escape", "req": "r1", "file": "a.py",
                                "line": 3, "note": "would escape"},
                       content_hash="h")
    resp = client.post("/api/assistant/actions/a-traverse/apply")
    assert resp.status_code == 400
    # The traversal target directory must not have been created.
    escape_dir = tmp_path / "escape"
    assert not escape_dir.exists()


def _drafted_action_on_shared_session(app):
    repo = _repo(app)
    repo.create_session(session_id="s-ro", provider="ollama", source="shared")
    return repo.create_action(
        action_id="a-ro", session_id="s-ro", action_type="dismiss_finding",
        payload={"project": "proj", "req": "R1", "file": "a.py", "line": 1, "reason": "false positive"}, content_hash="h")


def test_apply_refuses_shared_session_action(client, app):
    _drafted_action_on_shared_session(app)
    resp = client.post("/api/assistant/actions/a-ro/apply")
    assert resp.status_code == 403
    # And the action was NOT claimed: still drafted.
    assert _repo(app).get_action("a-ro")["status"] == "drafted"


def test_reject_refuses_shared_session_action(client, app):
    _drafted_action_on_shared_session(app)
    resp = client.post("/api/assistant/actions/a-ro/reject")
    assert resp.status_code == 403
    assert _repo(app).get_action("a-ro")["status"] == "drafted"


def test_catalog_marks_write_shaped_skills(client):
    body = client.get("/api/assistant/skills").get_json()
    flags = {s["name"]: s["requiresWrite"] for s in body["skills"]}
    assert flags["verify-finding"] is True
    assert flags["create-standard"] is True
    assert flags["explain-score"] is False
    assert flags["explain-finding"] is False
