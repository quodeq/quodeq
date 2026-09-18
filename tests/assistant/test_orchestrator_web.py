"""Orchestrator web-access toggle: tool registration and CLI config threading."""
from quodeq.assistant.orchestrator import TurnEngines, TurnRequest, run_turn

from ._orchestrator_helpers import _request


def test_web_enabled_registers_web_tools_for_local_provider(setup):
    repo, ctx = setup
    seen = {}

    def fake_turn(*, messages, config, session, **_):
        seen["names"] = session.registry.names()
        seen["system"] = messages[0]["content"]
        return "ok"

    run_turn(_request(web_enabled=True), repository=repo, tool_ctx=ctx,
             engines=TurnEngines(turn_fn=fake_turn, capability_fn=lambda *a, **k: True))
    assert "search_web" in seen["names"] and "fetch_url" in seen["names"]
    assert "# Web access" in seen["system"]


def test_web_tools_absent_by_default(setup):
    repo, ctx = setup
    seen = {}

    def fake_turn(*, messages, config, session, **_):
        seen["names"] = session.registry.names()
        seen["system"] = messages[0]["content"]
        return "ok"

    run_turn(_request(), repository=repo, tool_ctx=ctx,
             engines=TurnEngines(turn_fn=fake_turn, capability_fn=lambda *a, **k: True))
    assert "search_web" not in seen["names"] and "fetch_url" not in seen["names"]
    assert "# Web access" not in seen["system"]


def test_web_enabled_ignored_for_cloud_api_provider(setup):
    repo, ctx = setup
    seen = {}

    def fake_turn(*, messages, config, session, **_):
        seen["names"] = session.registry.names()
        return "ok"

    req = TurnRequest(session_id="s1", text="hi", ui_state=None,
                      api_base="https://openrouter.ai/api/v1", api_key="k",
                      provider="openrouter", model="m", web_enabled=True)
    run_turn(req, repository=repo, tool_ctx=ctx,
             engines=TurnEngines(turn_fn=fake_turn, capability_fn=lambda *a, **k: True))
    assert "search_web" not in seen["names"] and "fetch_url" not in seen["names"]


def test_web_enabled_threads_to_cli_config(setup, monkeypatch):
    repo, ctx = setup
    monkeypatch.setattr("quodeq.assistant.orchestrator.get_provider_configs",
                        lambda: {"claude": {"type": "cli"}})
    seen = {}

    def fake_cli_turn(*, config, **kwargs):
        seen["config"] = config
        return "cli answer"

    monkeypatch.setattr("quodeq.assistant.orchestrator.run_cli_turn", fake_cli_turn)
    req = TurnRequest(session_id="s1", text="hi", ui_state=None, api_base="",
                      api_key=None, provider="claude", model="sonnet",
                      web_enabled=True)
    run_turn(req, repository=repo, tool_ctx=ctx)
    assert seen["config"].web_enabled is True
