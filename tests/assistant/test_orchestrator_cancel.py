"""Orchestrator stop-turn cancellation and error-frame hygiene."""
from quodeq.assistant.orchestrator import TurnEngines, TurnRequest, run_turn

from ._orchestrator_helpers import _request


# ---- stop-turn cancellation -------------------------------------------------

def test_cancelled_cli_turn_emits_stopped_and_persists_partial(setup, monkeypatch):
    from quodeq.assistant.cancel import TurnCancelled
    repo, ctx = setup
    monkeypatch.setattr("quodeq.assistant.orchestrator.get_provider_configs",
                        lambda: {"claude": {"type": "cli"}})

    def cancelled_cli_turn(**kwargs):
        raise TurnCancelled("partial answer")

    monkeypatch.setattr("quodeq.assistant.orchestrator.run_cli_turn", cancelled_cli_turn)
    req = TurnRequest(session_id="s1", text="hi", ui_state=None, api_base="", api_key=None,
                      provider="claude", model="sonnet")
    run_turn(req, repository=repo, tool_ctx=ctx)
    msgs = repo.list_messages("s1")
    # the partial answer the user watched stream must survive in the history
    assert (msgs[-1]["role"], msgs[-1]["content"]) == ("assistant", "partial answer")
    frames = [f for _, f in repo.events_after("s1", 0)]
    assert frames[-1]["type"] == "stopped"
    assert not any(f["type"] == "error" for f in frames)


def test_cancelled_turn_without_partial_persists_no_assistant_message(setup):
    from quodeq.assistant.cancel import TurnCancelled
    repo, ctx = setup

    def cancelled_turn(**_):
        raise TurnCancelled("")

    run_turn(_request(), repository=repo, tool_ctx=ctx, engines=TurnEngines(turn_fn=cancelled_turn,
             capability_fn=lambda *a, **k: True))
    assert [m["role"] for m in repo.list_messages("s1")] == ["user"]
    frames = [f for _, f in repo.events_after("s1", 0)]
    assert frames[-1]["type"] == "stopped"


def test_turn_failure_emits_generic_message_not_raw_exception(setup):
    repo, ctx = setup

    def failing_turn(**_):
        raise ValueError("api key file /home/x/.secret missing")

    run_turn(_request(), repository=repo, tool_ctx=ctx, engines=TurnEngines(turn_fn=failing_turn,
             capability_fn=lambda *a, **k: True))
    frames = [f for _, f in repo.events_after("s1", 0)]
    error_events = [f for f in frames if f["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["message"] == (
        "The assistant hit an unexpected error. Check the server logs for details."
    )
    assert "/home/x/.secret" not in error_events[0]["message"]


def test_run_turn_threads_cancel_token_to_adapter(setup):
    from quodeq.assistant.cancel import CancelToken
    repo, ctx = setup
    seen = {}

    def fake_turn(*, session, **_):
        seen["default"] = session.cancel
        return "hi"

    run_turn(_request(), repository=repo, tool_ctx=ctx, engines=TurnEngines(turn_fn=fake_turn,
             capability_fn=lambda *a, **k: True))
    assert isinstance(seen["default"], CancelToken)

    token = CancelToken()

    def fake_turn2(*, session, **_):
        seen["explicit"] = session.cancel
        return "hi"

    run_turn(_request(), repository=repo, tool_ctx=ctx,
             engines=TurnEngines(turn_fn=fake_turn2, capability_fn=lambda *a, **k: True),
             cancel=token)
    assert seen["explicit"] is token
