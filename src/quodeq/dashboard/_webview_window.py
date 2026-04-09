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
    padding: 12px 11px;
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
  .sidebar { padding-top: 26px !important; }
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
        job = self._get_running_evaluation() if self._window else None
        if job:
            try:
                choice = self._window.evaluate_js(self._build_close_dialog_js(job))
                if choice == 'back':
                    return
                if choice == 'keep':
                    os._exit(0)
            except Exception:
                pass
        if self._api_pid:
            _kill_api(self._api_pid)
        if self._instance:
            self._instance.shutdown()
        os._exit(0)

    def _get_running_evaluation(self) -> dict | None:
        """Return the first running evaluation job, or None."""
        try:
            import urllib.request
            import json as _json
            url = self._window.get_current_url().split("#")[0].rstrip("/")
            base = url.rsplit("/", 1)[0] if "/" in url.lstrip("http") else url
            req = urllib.request.Request(f"{base}/api/evaluations")
            with urllib.request.urlopen(req, timeout=2) as resp:
                jobs = _json.loads(resp.read())
                for j in (jobs if isinstance(jobs, list) else []):
                    if j.get("status") == "running":
                        return j
        except Exception:
            pass
        return None

    @staticmethod
    def _build_close_dialog_js(job: dict) -> str:
        """Build JS for the close confirmation dialog with job info."""
        phase = job.get("phase", "analyzing")
        dim = job.get("currentDimension", "")
        repo = job.get("repo", "")
        # Build info line
        info_parts = []
        if repo:
            name = repo.rsplit("/", 1)[-1] if "/" in repo else repo
            info_parts.append(f"Project: <b>{name}</b>")
        if dim:
            info_parts.append(f"Dimension: <b>{dim}</b>")
        if phase:
            info_parts.append(f"Phase: <b>{phase}</b>")
        info_html = "<br>".join(info_parts) if info_parts else "Running..."

        return """
            (function() {
                var d = document.createElement('div');
                d.id = '_qd_close_dialog';
                d.style.cssText = 'position:fixed;inset:0;z-index:999999;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center';
                d.innerHTML = '<div style="background:var(--color-surface,#1c2128);border:1px solid var(--color-border,#333);border-radius:12px;padding:24px 28px;max-width:420px;color:var(--color-text,#e6edf3);font-family:inherit">'
                    + '<h3 style="margin:0 0 12px;font-size:1rem">Evaluation in progress</h3>'
                    + '<div style="margin:0 0 16px;padding:10px 14px;background:var(--color-surface-alt,#161b22);border-radius:6px;font-size:0.82rem;line-height:1.6;color:var(--color-text-muted,#8b949e)">""" + info_html + """</div>'
                    + '<div style="display:flex;flex-direction:column;gap:8px">'
                    + '<button id="_qd_close_keep" style="padding:10px 16px;border:1px solid var(--color-border,#333);border-radius:6px;background:var(--color-surface-alt,#161b22);color:var(--color-text,#e6edf3);cursor:pointer;font-size:0.85rem">Close window (evaluation continues in background)</button>'
                    + '<button id="_qd_close_cancel" style="padding:10px 16px;border:1px solid #da3633;border-radius:6px;background:transparent;color:#f85149;cursor:pointer;font-size:0.85rem">Cancel evaluation and close</button>'
                    + '<button id="_qd_close_back" style="padding:10px 16px;border:none;border-radius:6px;background:transparent;color:var(--color-text-muted,#8b949e);cursor:pointer;font-size:0.85rem">Go back</button>'
                    + '</div></div>';
                document.body.appendChild(d);
                return new Promise(function(resolve) {
                    document.getElementById('_qd_close_keep').onclick = function() { d.remove(); resolve('keep'); };
                    document.getElementById('_qd_close_cancel').onclick = function() { d.remove(); resolve('cancel'); };
                    document.getElementById('_qd_close_back').onclick = function() { d.remove(); resolve('back'); };
                    d.onclick = function(e) { if (e.target === d) { d.remove(); resolve('back'); } };
                });
            })()
        """

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


def _icon_path(ext: str) -> str | None:
    """Resolve the quodeq icon path for the given extension (.icns or .ico)."""
    p = Path(__file__).resolve().parent.parent.parent.parent / "packaging"
    if ext == ".icns":
        p = p / "macos" / "icon.icns"
    elif ext == ".ico":
        p = p / "windows" / "icon.ico"
    else:
        return None
    return str(p) if p.exists() else None


def _set_app_icon() -> None:
    """Set the application icon (dock on macOS, taskbar on Windows)."""
    if sys.platform == "darwin":
        try:
            from AppKit import NSApplication, NSImage  # type: ignore[import-untyped]
            path = _icon_path(".icns")
            if path:
                icon = NSImage.alloc().initWithContentsOfFile_(path)
                if icon:
                    NSApplication.sharedApplication().setApplicationIconImage_(icon)
        except ImportError:
            pass
    elif sys.platform == "win32":
        try:
            import ctypes
            path = _icon_path(".ico")
            if path:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("quodeq.dashboard")
                # Load icon and set for the process
                icon_flags = 0x00000010 | 0x00000001  # LR_LOADFROMFILE | LR_DEFAULTSIZE
                hicon = ctypes.windll.user32.LoadImageW(0, path, 1, 0, 0, icon_flags)
                if hicon:
                    ctypes.windll.user32.SendMessageW(
                        ctypes.windll.kernel32.GetConsoleWindow(), 0x0080, 0, hicon,
                    )
        except (AttributeError, OSError):
            pass


def main() -> None:
    _set_app_icon()
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
