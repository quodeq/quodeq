from __future__ import annotations

from typing import Any

import pytest

from quodeq.verifier.client import OllamaClient


class StubOllamaClient(OllamaClient):
    """Drop-in replacement for OllamaClient that returns pre-recorded responses.

    Tests inject one or more canned responses via the `script` attribute. Each
    call to `chat()` pops the next response off the front of the script.
    """

    def __init__(self, script: list[dict[str, Any]]) -> None:
        # intentionally do NOT call super().__init__ — we never hit the network
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        model: str,
        temperature: float = 0.2,
        keep_alive: str = "10m",
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "schema": schema,
                "model": model,
                "temperature": temperature,
            }
        )
        if not self.script:
            raise AssertionError("StubOllamaClient script exhausted")
        return self.script.pop(0)

    def close(self) -> None:
        pass


@pytest.fixture
def stub_client():
    """Factory that builds a StubOllamaClient from a list of canned responses."""

    def _make(*responses: dict[str, Any]) -> StubOllamaClient:
        return StubOllamaClient(list(responses))

    return _make
