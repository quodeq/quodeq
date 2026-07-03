"""Server-side gate deciding whether the embedded terminal may run.

Defense in depth: loopback bind + no API-key remote mode + Origin match. The
WS handshake is a GET, which the global CSRF hook (api/security.py) exempts, so
the Origin check MUST live here."""
from __future__ import annotations

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _hostname(host_header: str) -> str:
    h = (host_header or "").strip()
    if h.startswith("["):            # [::1]:7863  -> ::1
        end = h.find("]")
        return h[1:end] if end != -1 else h[1:]
    return h.rsplit(":", 1)[0] if ":" in h else h   # localhost:7863 -> localhost


def terminal_gate_reason(*, host: str, api_key: str | None, origin: str | None,
                         request_host: str) -> str | None:
    if host not in _LOOPBACK_HOSTS:
        return "The terminal is available only when quodeq is bound to localhost."
    if _hostname(request_host) not in _LOOPBACK_HOSTS:
        return "The terminal is only reachable via a localhost address."
    if api_key:
        return "The terminal is disabled while remote access (QUODEQ_API_KEY) is enabled."
    if not origin:
        return "Missing Origin header."
    if origin not in {f"http://{request_host}", f"https://{request_host}"}:
        return "Origin not allowed."
    return None
