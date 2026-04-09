"""Cloud API provider testing — connection verification."""
from __future__ import annotations

import ipaddress
import logging
import socket
import time
import urllib.parse

try:
    import openai
except ImportError:
    openai = None  # type: ignore[assignment]

_log = logging.getLogger(__name__)

_ALLOWED_SCHEMES = {"http", "https"}


def _is_private_url(url: str) -> bool:
    """Return True if *url* targets a private/internal network address."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            return True
        hostname = parsed.hostname or ""
        if not hostname:
            return True
        # Allow localhost explicitly (needed for Ollama)
        if hostname in ("localhost", "127.0.0.1", "::1"):
            return False
        for info in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(info[4][0])
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                return True
    except (ValueError, OSError):
        return True
    return False


def check_cloud_connection(
    *,
    api_base: str,
    model: str,
    api_key: str,
) -> dict:
    """Test a cloud API provider connection with a minimal request."""
    if openai is None:
        return {"success": False, "error": "openai package not installed. Install with: pip install 'quodeq[api]'"}
    if not api_base:
        return {"success": False, "error": "API base URL is required"}
    if _is_private_url(api_base):
        return {"success": False, "error": "Cannot connect to private/internal network addresses"}

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
        raw = str(exc)
        # Strip potential API key fragments from error messages
        if api_key and len(api_key) > 8 and api_key in raw:
            raw = raw.replace(api_key, "***")
        brief = raw[:120] if raw else "unknown error"
        return {"success": False, "error": f"{error_type}: {brief}"}
