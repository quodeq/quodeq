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
