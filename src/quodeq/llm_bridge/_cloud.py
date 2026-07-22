"""Cloud API provider testing — connection verification."""
from __future__ import annotations

import logging
import time

from quodeq.shared.url_validation import validate_url_safe

try:
    import openai
except ImportError:
    openai = None  # type: ignore[assignment]

_log = logging.getLogger(__name__)

_MIN_KEY_LEN_FOR_REDACTION = 8
_MAX_ERROR_BRIEF_LEN = 120


def _create_client(api_base: str, api_key: str) -> "openai.OpenAI":
    """Create an OpenAI client.

    Extracted as a factory so callers can override or mock client creation
    (e.g. for testing or custom transport adapters).
    """
    return openai.OpenAI(base_url=api_base, api_key=api_key)


def check_cloud_connection(
    *,
    api_base: str,
    model: str,
    api_key: str,
) -> dict:
    """Test a cloud API provider connection with a minimal request.

    The caller supplies ``api_base`` and ``api_key``, providing an adapter-
    pattern seam: callers control *which* endpoint and credentials are used,
    and ``_create_client`` can be monkey-patched for testing or custom transports.
    """
    if openai is None:
        return {"success": False, "error": "openai package not installed. Install with: pip install 'quodeq[api]'"}
    if not api_base:
        return {"success": False, "error": "API base URL is required"}
    try:
        validate_url_safe(api_base)
    except ValueError:
        return {"success": False, "error": "Cannot connect to private/internal network addresses"}

    try:
        with _create_client(api_base, api_key) as client:
            start = time.monotonic()
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
            latency = int((time.monotonic() - start) * 1000)
            return {"success": True, "model": model, "latency_ms": latency}
    except Exception as exc:
        # Surface the exception type and HTTP status codes without leaking
        # internal details like file paths, stack traces, or server headers.
        error_type = type(exc).__name__
        raw = str(exc)
        # Strip potential API key fragments from error messages
        if api_key and len(api_key) > _MIN_KEY_LEN_FOR_REDACTION and api_key in raw:
            raw = raw.replace(api_key, "***")
        # Log the redacted message, not the raw exception, so the key never
        # lands in application logs either.
        _log.debug("Cloud connection check failed: %s: %s", error_type, raw)
        brief = raw[:_MAX_ERROR_BRIEF_LEN] if raw else "unknown error"
        return {"success": False, "error": f"{error_type}: {brief}"}
