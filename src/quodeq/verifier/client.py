"""Thin HTTP client for the Ollama chat API."""

from __future__ import annotations

import json
from typing import Any

import httpx

from quodeq.verifier.errors import (
    MalformedResponseError,
    OllamaUnreachableError,
    VerifierTimeoutError,
)


class OllamaClient:
    """Synchronous HTTP client wrapping POST /api/chat with strict JSON schema."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout_seconds,
            transport=transport,
        )

    def chat(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        model: str,
        temperature: float = 0.2,
        keep_alive: str = "10m",
    ) -> dict[str, Any]:
        """Send a chat request with strict JSON-schema enforcement.

        Returns the parsed response dict (the model's structured output).
        Raises VerifierError subclasses on failure.
        """
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": schema,
            "options": {"temperature": temperature},
            "stream": False,
            "keep_alive": keep_alive,
        }
        try:
            resp = self._client.post("/api/chat", json=payload)
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise OllamaUnreachableError(str(exc)) from exc
        except httpx.TimeoutException as exc:
            raise VerifierTimeoutError(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            raise MalformedResponseError(
                f"HTTP {exc.response.status_code} from Ollama: {exc.response.text}"
            ) from exc

        body = resp.json()
        content = body.get("message", {}).get("content", "")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise MalformedResponseError(
                f"Could not parse model JSON output: {content!r}"
            ) from exc

    def close(self) -> None:
        self._client.close()
