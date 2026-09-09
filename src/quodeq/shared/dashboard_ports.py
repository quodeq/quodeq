"""Dashboard alt-port constants shared by the API's CSP header and the UI.

Mirrors shared/defaults.json's "dashboard_port" and ui/src/config.js's
DASHBOARD_BASE_PORT (tests/shared/test_dashboard_ports.py pins the defaults.json
drift). DASHBOARD_BASE_PORT is a literal here, not shared._env.get_dashboard_port():
that reads QUODEQ_DASHBOARD_PORT at call time, but this module is imported once
at API process start to build security.py's _ALT_PORT_ORIGINS, and it has to
match config.js's compile-time constant, not a runtime override taken after
the header is already built. PORT_SCAN_SPAN mirrors useServerHealth.js's
PORT_SCAN_SPAN: the base range the dashboard walks upward through when its
port is taken (dashboard/_networking.py).

useServerHealth.altPortCandidates() also probes the currentPort..+4
neighbourhood for a non-default QUODEQ_DASHBOARD_PORT; that neighbourhood is
out of scope here and stays uncovered by connect-src beyond 'self' (not
widened to dashboard/_networking.py's _MAX_PORT_SCAN_TRIES).
"""
from __future__ import annotations

DASHBOARD_BASE_PORT = 7863
PORT_SCAN_SPAN = 5


def alt_ports() -> tuple[int, ...]:
    """Return the dashboard alt ports the API's CSP allows explicitly."""
    return tuple(range(DASHBOARD_BASE_PORT, DASHBOARD_BASE_PORT + PORT_SCAN_SPAN))


def alt_port_origins() -> str:
    """Return the connect-src token text for every port in alt_ports()."""
    return " ".join(
        f"http://127.0.0.1:{p} http://localhost:{p} "
        f"ws://127.0.0.1:{p} ws://localhost:{p}"
        for p in alt_ports()
    )
