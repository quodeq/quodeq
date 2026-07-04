import pytest

from quodeq.assistant.tools import ToolContext, build_registry
from quodeq.data.sqlite.assistant_repository import AssistantRepository

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


def test_draft_dismiss_canonicalizes_from_session(project_ctx):
    out = build_registry(project_ctx).dispatch("draft_action", {
        "action_type": "dismiss_finding",
        "payload": {"req": "r1", "file": "a.py", "line": 3,
                    "reason": "guarded two lines above",
                    "project": "spoofed-by-model"},
    })
    assert out["ok"] is True
    stored = project_ctx.repository.get_action(out["result"]["action_id"])
    assert stored["payload"]["project"] == "proj"  # session wins over model payload
    assert stored["payload"]["reason"] == "guarded two lines above"
    frames = [f for _, f in project_ctx.repository.events_after("s1", 0)]
    draft = next(f for f in frames if f["type"] == "action_draft")
    assert draft["summary"] == {"req": "r1", "file": "a.py", "line": 3,
                                "reason": "guarded two lines above"}


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
