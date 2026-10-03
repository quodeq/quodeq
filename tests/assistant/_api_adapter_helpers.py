"""Shared fixtures for the API adapter tests (``test_api_adapter*.py``):
scripted fake OpenAI-compatible clients and the turn/session/config builders
every test in that group needs. Mirrors ``_cli_adapter_helpers.py``'s split
for the CLI adapter's own test group.
"""
from types import SimpleNamespace

from quodeq.assistant.adapters.api import ApiTurnConfig, ApiTurnSession
from quodeq.assistant.tools.registry import ToolRegistry, ToolSpec


def _delta(content=None, tool_calls=None, finish=None):
    d = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(delta=d, finish_reason=finish)
    return SimpleNamespace(choices=[choice])


def _tool_call_delta(index, call_id=None, name=None, args=""):
    fn = SimpleNamespace(name=name, arguments=args)
    return SimpleNamespace(index=index, id=call_id, function=fn)


class FakeClient:
    """Yields scripted streams; one script (list of chunks) per create() call."""

    def __init__(self, scripts):
        self._scripts = list(scripts)
        self.calls = []
        completions = SimpleNamespace(create=self._create)
        self.chat = SimpleNamespace(completions=completions)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self._scripts.pop(0))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class ClosableFakeClient(FakeClient):
    def __init__(self, scripts):
        super().__init__(scripts)
        self.closed = False

    def close(self):
        self.closed = True


def _registry():
    reg = ToolRegistry()
    reg.register(ToolSpec(
        "get_scores", "scores", {"type": "object", "properties": {}},
        lambda: {"security": {"score": 61.5, "grade": "C"}}))
    return reg


def _session(emit, cancel=None):
    if cancel is None:
        return ApiTurnSession(registry=_registry(), emit=emit)
    return ApiTurnSession(registry=_registry(), emit=emit, cancel=cancel)


def _config(native=True):
    return ApiTurnConfig(api_base="http://x/v1", api_key=None,
                         model="m", native_tools=native)
