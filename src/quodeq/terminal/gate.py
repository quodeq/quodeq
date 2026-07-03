"""Server-side gate deciding whether the embedded terminal may run.

Two layers:
- ``terminal_env_reason`` — the ENVIRONMENT gate: is the terminal available at
  all for this request? (server bound to loopback, request Host is a loopback
  name, no API-key remote mode). This is what ``/status`` reports and it must
  NOT require an Origin header — browsers omit Origin on same-origin GETs, so
  gating a read on it would wrongly report the terminal disabled.
- ``terminal_gate_reason`` — the FULL gate for the WebSocket handshake: the env
  checks PLUS an Origin match. The handshake is a GET (exempt from the global
  CSRF hook, api/security.py) yet browsers DO send Origin on WS handshakes, so
  the cross-site-WebSocket-hijack defense lives here."""
from __future__ import annotations

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _hostname(host_header: str) -> str:
    h = (host_header or "").strip()
    if h.startswith("["):            # [::1]:7863  -> ::1
        end = h.find("]")
        return h[1:end] if end != -1 else h[1:]
    return h.rsplit(":", 1)[0] if ":" in h else h   # localhost:7863 -> localhost


def terminal_env_reason(*, host: str, api_key: str | None,
                        request_host: str) -> str | None:
    """Environment availability gate (no Origin check). None = available."""
    if host not in _LOOPBACK_HOSTS:
        return "The terminal is available only when quodeq is bound to localhost."
    if _hostname(request_host) not in _LOOPBACK_HOSTS:
        return "The terminal is only reachable via a localhost address."
    if api_key:
        return "The terminal is disabled while remote access (QUODEQ_API_KEY) is enabled."
    return None


def terminal_gate_reason(*, host: str, api_key: str | None, origin: str | None,
                         request_host: str) -> str | None:
    """Full gate for the WS handshake: env checks + Origin match. None = allowed."""
    reason = terminal_env_reason(host=host, api_key=api_key, request_host=request_host)
    if reason is not None:
        return reason
    if not origin:
        return "Missing Origin header."
    if origin not in {f"http://{request_host}", f"https://{request_host}"}:
        return "Origin not allowed."
    return None
