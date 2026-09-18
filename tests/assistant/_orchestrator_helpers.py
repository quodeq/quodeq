"""TurnRequest builder shared by the test_orchestrator* siblings."""
from quodeq.assistant.orchestrator import TurnRequest


def _request(text="hello", ui_state=None, **kw):
    return TurnRequest(session_id="s1", text=text, ui_state=ui_state,
                       api_base="http://x/v1", api_key=None,
                       provider="ollama", model="m", **kw)
