"""HTML/CSS/JS string constants for pywebview window controls."""
from __future__ import annotations

import json
import sys

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

INJECT_JS = _CONTROLS_JS % json.dumps(_CONTROLS_HTML)

CLOSING_OVERLAY_JS = """
    (function() {
        var d = document.createElement('div');
        d.style.cssText = 'position:fixed;inset:0;z-index:999999;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;pointer-events:all';
        d.innerHTML = '<div style="color:var(--color-text-muted,#8b949e);font-family:inherit;font-size:0.95rem;text-align:center">'
            + '<div style="margin-bottom:10px;opacity:0.7">Closing...</div></div>';
        document.body.appendChild(d);
    })()
"""
