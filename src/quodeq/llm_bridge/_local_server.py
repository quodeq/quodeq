"""Shapes and URL handling shared by the local model-server bridges (Ollama, llama.cpp, omlx)."""
from __future__ import annotations

_HTTP_SCHEME = "http://"  # dropped from the address shown to the user
_OPENAI_PATH = "/v1"  # OpenAI-compatible prefix; the native endpoints sit one level up


def normalize_base(base_url: str) -> str:
    """Strip a trailing ``/v1`` (or ``/v1/``) so ``/health`` and ``/v1/models`` both work.

    Quodeq stores ``api_base`` as the OpenAI-compatible ``/v1`` URL for the
    analysis runner; the servers' native endpoints sit one level up, so
    either form is accepted.
    """
    stripped = base_url.rstrip("/")
    if stripped.endswith(_OPENAI_PATH):
        stripped = stripped[: -len(_OPENAI_PATH)]
    return stripped


def server_address(base_url: str) -> str:
    """*base_url* as the status payload shows it: without the ``http://`` scheme."""
    return base_url.replace(_HTTP_SCHEME, "")


def bare_model_entry(name: str) -> dict:
    """A model-list entry for a server that reports only the model's name."""
    return {"name": name, "size": 0, "quantization": "", "family": ""}


def concurrency_result(
    recommended: int, vram_per_context: int | float, gpu_memory: int | float,
    reason: str | None = None,
) -> dict:
    """The concurrency-test payload; *reason* is present only when the estimate fell back to 1."""
    result = {
        "recommended": recommended,
        "vram_per_context": vram_per_context,
        "gpu_memory": gpu_memory,
    }
    if reason is not None:
        result["reason"] = reason
    return result
