"""On Linux without a GTK/WebKit2GTK backend, the dashboard must fall back to
the browser instead of crashing (exercises dashboard/_server.py:142).

Deterministic on any host: sys.platform and the backend probe are patched, so
it asserts the fallback contract without needing a real Linux/GTK environment.
"""
from __future__ import annotations

from quodeq.dashboard import _server
from quodeq.dashboard._probes import NativeShell


def test_serve_native_falls_back_to_browser_when_gtk_missing(monkeypatch) -> None:
    opened: list[str] = []
    served: list[bool] = []
    monkeypatch.setattr(_server.sys, "platform", "linux")
    shell = NativeShell(
        webview_importable=lambda: True,
        linux_backend_available=lambda: False,
        open_browser=opened.append,
    )

    _server._serve_native(
        "http://127.0.0.1:7863", None, lambda: None,
        shell=shell, serve_blocking=lambda proc, stop: served.append(True),
    )

    assert opened == ["http://127.0.0.1:7863"], "should open the dashboard URL in a browser"
    assert served == [True], "should keep serving the API after falling back"
