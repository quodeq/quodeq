import json

import pytest

from quodeq.assistant.tools import ToolContext, build_registry
from quodeq.data.sqlite.assistant_repository import AssistantRepository


def _seed_run_ctx(tmp_path, violations, *, dbname="assistant_run.db"):
    """Run-scoped ctx whose eval JSON carries `violations` so the dismiss/verify
    match-check (finding_keys_in_scope) can confirm the drafted key is real."""
    eval_root = tmp_path / "evals"
    run_dir = eval_root / "proj" / "run1"
    (run_dir / "evaluation").mkdir(parents=True)
    (run_dir / "evaluation" / "security.json").write_text(json.dumps({
        "dimension": "security", "overallScore": 50, "overallGrade": "C",
        "principles": [], "violations": violations,
        "totals": {"violations": len(violations)},
    }))
    store = AssistantRepository(tmp_path / dbname)
    store.create_session(session_id="s1", provider="ollama")
    return ToolContext(
        repository=store, session_id="s1", run_dir=run_dir, repo_root=None,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
        project_id="proj", reports_dir=eval_root,
    )

_VALID_STANDARD = {
    "id": "api-errors", "name": "API Error Contract", "description": "d",
    "weight": 1.0, "source": "assistant",
    "principles": [{"name": "P1", "description": "", "requirements": [
        {"id": "r1", "text": "Endpoints return RFC7807", "description": "", "refs": []},
    ]}],
}


@pytest.fixture()
def ctx(tmp_path):
    store = AssistantRepository(tmp_path / "assistant.db")
    store.create_session(session_id="s1", provider="ollama")
    return ToolContext(
        repository=store, session_id="s1", run_dir=None, repo_root=None,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
    )


def test_draft_action_persists_and_emits(ctx):
    reg = build_registry(ctx)
    out = reg.dispatch("draft_action", {
        "action_type": "create_standard", "payload": _VALID_STANDARD,
    })
    assert out["ok"] is True
    action_id = out["result"]["action_id"]
    stored = ctx.repository.get_action(action_id)
    assert stored["status"] == "drafted"
    assert stored["payload"]["id"] == "api-errors"
    frames = [f for _, f in ctx.repository.events_after("s1", 0)]
    assert any(f["type"] == "action_draft" and f["actionId"] == action_id for f in frames)


def test_draft_action_rejects_unknown_type(ctx):
    out = build_registry(ctx).dispatch("draft_action", {
        "action_type": "delete_everything", "payload": {},
    })
    assert out["ok"] is False


def test_draft_action_rejects_invalid_payload(ctx):
    out = build_registry(ctx).dispatch("draft_action", {
        "action_type": "create_standard", "payload": {"name": "no id"},
    })
    assert out["ok"] is False


def test_actions_registry_covers_types(ctx):
    from quodeq.assistant.tools._actions import ACTIONS, ACTION_TYPES
    assert set(ACTIONS) == set(ACTION_TYPES)
    for spec in ACTIONS.values():
        assert callable(spec.validate) and callable(spec.summarize) and callable(spec.apply)


@pytest.fixture()
def project_ctx(tmp_path):
    store = AssistantRepository(tmp_path / "assistant_p.db")
    store.create_session(session_id="s1", provider="ollama")
    return ToolContext(
        repository=store, session_id="s1", run_dir=None, repo_root=None,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
        project_id="proj", reports_dir=tmp_path / "evals",
    )


def test_draft_dismiss_requires_reason(project_ctx):
    out = build_registry(project_ctx).dispatch("draft_action", {
        "action_type": "dismiss_finding",
        "payload": {"req": "r1", "file": "a.py", "line": 3},
    })
    assert out["ok"] is False
    assert "reason" in out["error"]


def test_draft_dismiss_canonicalizes_from_session(tmp_path):
    ctx = _seed_run_ctx(tmp_path, [
        {"principle": "P1", "req": "r1", "file": "a.py", "line": 3,
         "severity": "major", "title": "t", "reason": "r"}])
    out = build_registry(ctx).dispatch("draft_action", {
        "action_type": "dismiss_finding",
        "payload": {"req": "r1", "file": "a.py", "line": 3,
                    "reason": "guarded two lines above",
                    "project": "spoofed-by-model"},
    })
    assert out["ok"] is True
    stored = ctx.repository.get_action(out["result"]["action_id"])
    assert stored["payload"]["project"] == "proj"  # session wins over model payload
    assert stored["payload"]["reason"] == "guarded two lines above"
    frames = [f for _, f in ctx.repository.events_after("s1", 0)]
    draft = next(f for f in frames if f["type"] == "action_draft")
    assert draft["summary"] == {"req": "r1", "file": "a.py", "line": 3,
                                "reason": "guarded two lines above"}


def test_draft_dismiss_rejects_unmatched_key(tmp_path):
    # The model dismisses with the PRINCIPLE (the only id get_violations used to
    # expose) as req. No finding has that (req, file, line), so recording it
    # would be a silent no-op. The draft fails in-loop instead.
    ctx = _seed_run_ctx(tmp_path, [
        {"principle": "P1", "req": "r1", "file": "a.py", "line": 3,
         "severity": "major", "title": "t", "reason": "r"}])
    out = build_registry(ctx).dispatch("draft_action", {
        "action_type": "dismiss_finding",
        "payload": {"req": "P1", "file": "a.py", "line": 3, "reason": "fp"},
    })
    assert out["ok"] is False
    assert "no finding matches" in out["error"]


def test_draft_dismiss_accepts_sql_only_finding(tmp_path):
    # A finding surfaced by search_findings (SQL) but absent from the eval JSON
    # (the two stores can drift) must still be dismissable -- the match-check
    # unions both sources so it never falsely rejects a finding the model saw.
    from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository

    ctx = _seed_run_ctx(tmp_path, [])  # empty eval JSON
    SqliteFindingsRepository(ctx.run_dir).insert_finding({
        "p": "P1", "d": "security", "req": "SQL-1", "t": "violation",
        "severity": "major", "file": "z.py", "line": 42, "end_line": 42,
        "w": "t", "reason": "r", "snippet": "s", "vt": "code", "context": "",
        "scope": "file", "req_refs": [], "confidence": 90,
        "provenance_downgrade": 0,
    })
    out = build_registry(ctx).dispatch("draft_action", {
        "action_type": "dismiss_finding",
        "payload": {"req": "SQL-1", "file": "z.py", "line": 42, "reason": "fp"},
    })
    assert out["ok"] is True


def test_draft_dismiss_accepts_req_none_finding(tmp_path):
    # A finding with no req (practiceId-only identity) is dismissable with an
    # empty req, mirroring the dashboard. The old validator rejected empty req,
    # making such findings undismissable by the assistant.
    ctx = _seed_run_ctx(tmp_path, [
        {"principle": "P1", "file": "a.py", "line": 3,  # no req key
         "severity": "major", "title": "t", "reason": "r"}])
    out = build_registry(ctx).dispatch("draft_action", {
        "action_type": "dismiss_finding",
        "payload": {"file": "a.py", "line": 3, "reason": "fp"},  # req omitted
    })
    assert out["ok"] is True
    stored = ctx.repository.get_action(out["result"]["action_id"])
    assert stored["payload"]["req"] == ""


def test_draft_verify_requires_note_and_project(ctx, project_ctx):
    reg = build_registry(project_ctx)
    out = reg.dispatch("draft_action", {
        "action_type": "verify_finding",
        "payload": {"req": "r1", "file": "a.py", "line": 3},
    })
    assert out["ok"] is False and "note" in out["error"]
    out = build_registry(ctx).dispatch("draft_action", {
        "action_type": "verify_finding",
        "payload": {"req": "r1", "file": "a.py", "line": 3, "note": "n"},
    })
    assert out["ok"] is False  # ctx has no project_id -> actionable error


@pytest.fixture()
def evil_project_ctx(tmp_path):
    store = AssistantRepository(tmp_path / "assistant_evil.db")
    store.create_session(session_id="s1", provider="ollama")
    return ToolContext(
        repository=store, session_id="s1", run_dir=None, repo_root=None,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
        project_id="../evil",
        reports_dir=tmp_path / "evals",
    )


def test_draft_dismiss_rejects_evil_project_id(evil_project_ctx):
    """draft_action for dismiss_finding must fail when project_id is a traversal path."""
    out = build_registry(evil_project_ctx).dispatch("draft_action", {
        "action_type": "dismiss_finding",
        "payload": {"req": "r1", "file": "a.py", "line": 3, "reason": "fp"},
    })
    assert out["ok"] is False
    assert "invalid project" in out["error"].lower()


def test_draft_dismiss_rejects_bool_line(project_ctx):
    """line=True must be rejected (isinstance check tightened to exclude booleans)."""
    out = build_registry(project_ctx).dispatch("draft_action", {
        "action_type": "dismiss_finding",
        "payload": {"req": "r1", "file": "a.py", "line": True, "reason": "fp"},
    })
    assert out["ok"] is False
