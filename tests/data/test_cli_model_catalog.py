"""Tests for the live Claude Code / Codex model catalogs (data/cli_models.py).

A scripted session stands in for the CLI process: it records what quodeq
sends and replays the messages the real CLIs answer with (shapes captured
from Claude Code 2.1 and codex-cli 0.162).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from quodeq.data.cli_models import CatalogUnavailable, fetch_cli_model_catalog, supports_model_catalog

_SESSION = "quodeq.data.cli_models._JsonLinesSession"
_WHICH = "quodeq.shared.win_launch.shutil.which"


class _ScriptedSession:
    """Replays *replies* in order to every wait_for, skipping ones it rejects."""

    def __init__(self, replies: list[dict]) -> None:
        self.sent: list[dict] = []
        self._replies = list(replies)
        self.closed = False

    def __call__(self, *_args, **_kwargs) -> _ScriptedSession:
        return self

    def send(self, message: dict) -> None:
        self.sent.append(message)

    def wait_for(self, matches) -> dict:
        while self._replies:
            reply = self._replies.pop(0)
            if matches(reply):
                return reply
        raise CatalogUnavailable("timed out")

    def close(self) -> None:
        self.closed = True


def _fetch(client_id: str, session: _ScriptedSession) -> list[dict]:
    with patch(_WHICH, return_value=f"/bin/{client_id}"), patch(_SESSION, session):
        return fetch_cli_model_catalog(client_id, env={}, timeout_s=1)


def _claude_model(value: str, resolved: str, efforts: list[str] | None) -> dict:
    model = {"value": value, "resolvedModel": resolved, "displayName": value.title(), "description": "d"}
    if efforts is not None:
        model["supportedEffortLevels"] = efforts
    return model


_CLAUDE_REPLY = {"type": "control_response", "response": {"subtype": "success", "response": {"models": [
    _claude_model("default", "claude-opus-5-5", ["low", "max"]),
    _claude_model("opus", "claude-opus-5-5", ["low", "max"]),
    _claude_model("sonnet", "claude-sonnet-5-5", ["low"]),
    _claude_model("claude-haiku-4-5-20251001", "claude-haiku-4-5-20251001", None),
]}}}


class TestClaudeCatalog:
    def test_maps_aliases_and_pinned_versions(self) -> None:
        catalog = _fetch("claude", _ScriptedSession([{"type": "system"}, _CLAUDE_REPLY]))
        assert [(e["id"], e["isDefault"], e["pinned"], e["efforts"]) for e in catalog] == [
            ("opus", True, False, ["low", "max"]),
            ("sonnet", False, False, ["low"]),
            ("claude-haiku-4-5-20251001", False, True, []),
        ]

    def test_sends_only_the_initialize_request(self) -> None:
        session = _ScriptedSession([_CLAUDE_REPLY])
        _fetch("claude", session)
        assert [m["request"]["subtype"] for m in session.sent] == ["initialize"]
        assert session.closed

    @pytest.mark.parametrize("body", [{"response": {}}, {"response": "oops"}, "oops", None])
    def test_reply_without_a_model_list_is_unavailable(self, body) -> None:
        reply = {"type": "control_response", "response": body}
        with pytest.raises(CatalogUnavailable):
            _fetch("claude", _ScriptedSession([reply]))

    def test_no_alias_is_recommended_without_a_default_entry(self) -> None:
        models = [_claude_model("opus", None, ["low"]), _claude_model("sonnet", None, ["low"])]
        reply = {"type": "control_response", "response": {"response": {"models": models}}}
        assert not any(e["isDefault"] for e in _fetch("claude", _ScriptedSession([reply])))


def _codex_model(model_id: str, *, hidden: bool = False, default: bool = False) -> dict:
    return {
        "id": model_id, "displayName": model_id.upper(), "description": "d", "hidden": hidden,
        "isDefault": default, "defaultReasoningEffort": "medium",
        "supportedReasoningEfforts": [{"reasoningEffort": "low"}, {"reasoningEffort": "ultra"}],
    }


_CODEX_INIT_REPLY = {"id": 1, "result": {}}


class TestCodexCatalog:
    def test_follows_pages_and_drops_hidden_models(self) -> None:
        session = _ScriptedSession([
            _CODEX_INIT_REPLY,
            {"id": 2, "result": {"data": [_codex_model("sol", default=True), _codex_model("old", hidden=True)],
                                 "nextCursor": "p2"}},
            {"id": 3, "result": {"data": [_codex_model("luna")], "nextCursor": None}},
        ])
        catalog = _fetch("codex", session)
        assert [(e["id"], e["isDefault"], e["defaultEffort"], e["efforts"]) for e in catalog] == [
            ("sol", True, "medium", ["low", "ultra"]),
            ("luna", False, "medium", ["low", "ultra"]),
        ]
        assert [m.get("method") for m in session.sent] == ["initialize", "initialized", "model/list", "model/list"]
        assert session.sent[-1]["params"] == {"cursor": "p2"}

    def test_non_dict_result_is_unavailable(self) -> None:
        with pytest.raises(CatalogUnavailable):
            _fetch("codex", _ScriptedSession([_CODEX_INIT_REPLY, {"id": 2, "result": ["oops"]}]))

    def test_rejected_list_is_unavailable(self) -> None:
        session = _ScriptedSession([_CODEX_INIT_REPLY, {"id": 2, "error": {"message": "auth"}}])
        with pytest.raises(CatalogUnavailable):
            _fetch("codex", session)


def test_missing_cli_is_unavailable() -> None:
    with patch(_WHICH, return_value=None), pytest.raises(CatalogUnavailable):
        fetch_cli_model_catalog("claude", env={}, timeout_s=1)


@pytest.mark.parametrize(("client_id", "supported"), [("claude", True), ("codex", True), ("gemini", False)])
def test_supports_model_catalog(client_id: str, supported: bool) -> None:
    assert supports_model_catalog(client_id) is supported
