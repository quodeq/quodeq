"""Cloud API provider testing — connection verification."""
from __future__ import annotations

import logging
import time

try:
    import openai
except ImportError:
    openai = None  # type: ignore[assignment]

_log = logging.getLogger(__name__)


def check_cloud_connection(
    *,
    api_base: str,
    model: str,
    api_key: str,
) -> dict:
    """Test a cloud API provider connection with a minimal request."""
    if openai is None:
        return {"success": False, "error": "openai package not installed. Install with: pip install 'quodeq[api]'"}

    try:
        client = openai.OpenAI(base_url=api_base, api_key=api_key)
        start = time.monotonic()
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
        )
        latency = int((time.monotonic() - start) * 1000)
        return {"success": True, "model": model, "latency_ms": latency}
    except Exception as exc:
        _log.debug("Cloud connection check failed: %s", exc)
        # Surface the exception type and HTTP status codes without leaking
        # internal details like file paths, stack traces, or server headers.
        error_type = type(exc).__name__
        brief = str(exc)[:120] if str(exc) else "unknown error"
        return {"success": False, "error": f"{error_type}: {brief}"}
