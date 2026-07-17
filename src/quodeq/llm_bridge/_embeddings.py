"""Embeddings client for OpenAI-compatible local providers (Ollama et al.).

Deliberately separate from the chat clients (analysis/_api_runner.py,
assistant/adapters/_api.py): embeddings use short timeouts — never the 500s
chat read budget — and their model/base URL are configured independently of
the chat provider (CLI providers have no HTTP endpoint; llama.cpp serves one
model per process). All failures raise; callers own graceful degradation.
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Sequence

import httpx

try:
    import openai
except ImportError:
    openai = None  # type: ignore[assignment]

BATCH_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)
QUERY_TIMEOUT = httpx.Timeout(connect=10.0, read=10.0, write=30.0, pool=10.0)

ClientFactory = Callable[[], Any]


def _v1_base(base_url: str) -> str:
    base = base_url.rstrip("/")
    return base if base.endswith("/v1") else base + "/v1"


def _client_kwargs(
    base_url: str,
    api_key: str | None,
    timeout: httpx.Timeout | None,
) -> dict[str, Any]:
    """Build kwargs for openai.OpenAI instantiation (testable without patching)."""
    return {
        "base_url": _v1_base(base_url),
        "api_key": api_key or "ollama",
        "timeout": timeout or BATCH_TIMEOUT,
        "max_retries": 0,
    }


def embed_texts(
    texts: Sequence[str],
    *,
    model: str,
    base_url: str,
    api_key: str | None = None,
    timeout: httpx.Timeout | None = None,
    client_factory: ClientFactory | None = None,
) -> list[list[float]]:
    """Embed *texts* in one request, preserving input order.

    Raises on any failure (missing SDK, HTTP error, count mismatch); callers
    degrade gracefully. *client_factory* is the test seam — tests inject a
    scripted client instead of patching module internals.
    """
    if not texts:
        return []
    if client_factory is None:
        if openai is None:
            raise RuntimeError("openai package not installed")

        def client_factory() -> Any:
            return openai.OpenAI(**_client_kwargs(base_url, api_key, timeout))

    with client_factory() as client:
        resp = client.embeddings.create(model=model, input=list(texts))
    items = sorted(resp.data, key=lambda item: item.index)
    if len(items) != len(texts):
        raise RuntimeError(
            f"embedding count mismatch: sent {len(texts)}, got {len(items)}"
        )
    return [list(item.embedding) for item in items]


_availability_cache: dict[tuple[str, str], bool] = {}
_availability_lock = threading.Lock()


def embedding_model_available(
    model: str,
    base_url: str,
    *,
    lister: Callable[[str], list[dict[str, Any]]] | None = None,
) -> bool:
    """True when *model* is served at *base_url*. Cached per process.

    Ollama bases are probed via /api/tags (list_ollama_models); non-Ollama
    OpenAI-compatible bases return True permissively — they fail gracefully
    at call time. The cache keeps the per-call API path cheap.
    """
    key = (model, base_url)
    with _availability_lock:
        cached = _availability_cache.get(key)
    if cached is not None:
        return cached
    if lister is None:
        # Narrower than _providers._LOCAL_API_MARKERS on purpose: this gates "/api/tags exists", not "is local" — localhost llama.cpp/omlx must NOT match.
        if "11434" in base_url or "ollama" in base_url.lower():
            from quodeq.llm_bridge._ollama import list_ollama_models  # noqa: PLC0415
            lister = list_ollama_models
        else:
            with _availability_lock:
                _availability_cache[key] = True
            return True
    names = {m.get("name", "") for m in lister(base_url)}
    tagged = model if ":" in model else f"{model}:latest"
    result = model in names or tagged in names
    with _availability_lock:
        _availability_cache[key] = result
    return result


def reset_embedding_availability_cache() -> None:
    """Test hook: clear the per-process availability cache."""
    with _availability_lock:
        _availability_cache.clear()
