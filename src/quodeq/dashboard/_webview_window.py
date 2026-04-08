"""PyWebView window process — launched as a subprocess by _server.py."""
from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path

import webview

from quodeq.dashboard._build_npm import _quodeq_dir
from quodeq.dashboard._instance import InstanceController

_CONTROLS_MAC = """\
<style>
  .qd-traffic {
    position: fixed;
    top: 0;
    left: 0;
    display: flex;
    gap: 6px;
    z-index: 99999;
    padding: 6px 11px;
    pointer-events: auto;
  }
  .qd-traffic::after {
    content: "";
    position: absolute;
    top: 0; left: 0;
    width: 64px; height: 100%;
    z-index: -1;
  }
  .qd-dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    border: none;
    cursor: pointer;
    transition: background 0.2s;
    padding: 0;
    background: var(--color-text-muted, #484f58);
    opacity: 0.4;
  }
  .qd-traffic:hover .qd-dot,
  body:has(.sidebar:hover) .qd-dot { opacity: 1; }
  .qd-traffic:hover .qd-dot--close,
  body:has(.sidebar:hover) .qd-dot--close { background: #ff5f57; }
  .qd-traffic:hover .qd-dot--minimize,
  body:has(.sidebar:hover) .qd-dot--minimize { background: #febc2e; }
  .qd-traffic:hover .qd-dot--maximize,
  body:has(.sidebar:hover) .qd-dot--maximize { background: #28c840; }
  .sidebar { padding-top: 18px !important; }
  body:has(.qd-traffic:hover) .app-shell {
    grid-template-columns: var(--sidebar-expanded-width) 1fr;
  }
  body:has(.qd-traffic:hover) .sidebar {
    width: var(--sidebar-expanded-width);
  }
  body:has(.qd-traffic:hover) .sidebar-brand-text {
    opacity: 1;
  }
  body:has(.qd-traffic:hover) .sidebar-nav-label {
    opacity: 1;
  }
</style>
<div class="qd-traffic">
  <button class="qd-dot qd-dot--close" title="Close" onclick="pywebview.api.close()"></button>
  <button class="qd-dot qd-dot--minimize" title="Minimize" onclick="pywebview.api.minimize()"></button>
  <button class="qd-dot qd-dot--maximize" title="Fullscreen" onclick="pywebview.api.maximize()"></button>
</div>"""

_CONTROLS_WIN = """\
<style>
  .qd-winbtns {
    position: fixed;
    top: 0;
    right: 0;
    display: flex;
    z-index: 99999;
  }
  .qd-winbtn {
    width: 46px; height: 32px;
    border: none;
    background: transparent;
    color: var(--color-text-muted, #888);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    transition: background 0.1s;
  }
  .qd-winbtn:hover { background: var(--color-surface-alt, rgba(255,255,255,0.1)); }
  .qd-winbtn--close:hover { background: #e81123; color: #fff; }
  body { padding-top: 32px !important; }
</style>
<div class="qd-winbtns">
  <button class="qd-winbtn" title="Minimize" onclick="pywebview.api.minimize()">&#x2013;</button>
  <button class="qd-winbtn" title="Maximize" onclick="pywebview.api.maximize()">&#x2610;</button>
  <button class="qd-winbtn qd-winbtn--close" title="Close" onclick="pywebview.api.close()">&#x2715;</button>
</div>"""

_CONTROLS_HTML = _CONTROLS_WIN if sys.platform == "win32" else _CONTROLS_MAC

_CONTROLS_JS = """\
(function() {
  if (document.querySelector('.qd-traffic')) return;
  var d = document.createElement('div');
  d.innerHTML = %s;
  while (d.firstChild) document.body.insertBefore(d.firstChild, document.body.firstChild);

  document.addEventListener('keydown', function(e) {
    var mod = navigator.platform.indexOf('Mac') >= 0 ? e.metaKey : e.ctrlKey;
    if (mod && e.key === '[') { e.preventDefault(); history.back(); }
    if (mod && e.key === ']') { e.preventDefault(); history.forward(); }
  });
})();
"""

_INJECT_JS = _CONTROLS_JS % json.dumps(_CONTROLS_HTML)


class _WindowApi:
    """Python API exposed to JavaScript for window controls."""

    def __init__(self) -> None:
        self._window: webview.Window | None = None
        self._api_pid = 0
        self._instance: InstanceController | None = None

    def bind(self, window: webview.Window, api_pid: int = 0,
             instance: InstanceController | None = None) -> None:
        self._window = window
        self._api_pid = api_pid
        self._instance = instance

    def close(self) -> None:
        if self._api_pid:
            _kill_api(self._api_pid)
        if self._instance:
            self._instance.shutdown()
        os._exit(0)

    def minimize(self) -> None:
        if self._window:
            self._window.minimize()

    def maximize(self) -> None:
        if not self._window:
            return
        if sys.platform == "win32":
            if self._window.maximized:
                self._window.restore()
            else:
                self._window.maximize()
        else:
            self._window.toggle_fullscreen()


def _kill_api(pid: int) -> None:
    """Terminate the Flask API process."""
    try:
        sig = signal.SIGTERM if sys.platform != "win32" else signal.CTRL_BREAK_EVENT
        os.kill(pid, sig)
    except (OSError, ProcessLookupError):
        pass


def main() -> None:
    url = sys.argv[1]
    sock_path = Path(sys.argv[2])
    api_pid = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else 0

    instance = InstanceController(sock_path)
    api = _WindowApi()

    window = webview.create_window("quodeq", url, width=1280, height=800,
                                    frameless=True, easy_drag=True,
                                    background_color='#0d1117', hidden=True,
                                    js_api=api)
    api.bind(window, api_pid=api_pid, instance=instance)

    def _on_reload(new_url: str) -> None:
        window.load_url(new_url)
        window.on_top = True
        window.on_top = False

    def _on_loaded() -> None:
        window.show()
        window.evaluate_js(_INJECT_JS)

    window.events.loaded += _on_loaded

    instance.start_listening(on_reload=_on_reload)

    storage_dir = str(_quodeq_dir() / "webview")

    try:
        webview.start(private_mode=False, storage_path=storage_dir)
    finally:
        instance.shutdown()
        if api_pid:
            _kill_api(api_pid)


if __name__ == "__main__":
    main()
