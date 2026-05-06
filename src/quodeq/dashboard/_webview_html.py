"""HTML/CSS/JS string constants for pywebview window controls."""
from __future__ import annotations

import json
import sys

# Windows uses native chrome (frameless=False in _webview_window), so no
# in-page controls are injected. macOS and Linux use frameless windows with
# Mac-style traffic-light dots on the left — keeping them on the left avoids
# colliding with topbar actions that live on the right (e.g. Re-evaluate
# toggles).
_CONTROLS_MAC = """\
<style>
  /* Traffic-light dots sit INSIDE the topbar's empty left-padding area
     (the topbar has padding-left: 96px so its breadcrumb starts clear of
     the 64px wide sidebar column). No separate strip above the app. */
  .qd-traffic {
    position: fixed;
    top: 0;
    left: 0;
    display: flex;
    align-items: center;
    gap: 8px;
    z-index: 99999;
    padding: 0 12px;
    height: var(--app-header-h, 52px);
    pointer-events: auto;
  }
  .qd-dot {
    width: 12px; height: 12px;
    border-radius: 50%;
    border: none;
    cursor: pointer;
    transition: transform 0.15s, box-shadow 0.15s;
    padding: 0;
  }
  /* Canonical macOS colors — always rendered so users can see the controls
     without needing to hover. */
  .qd-dot--close    { background: #ff5f57; }
  .qd-dot--minimize { background: #febc2e; }
  .qd-dot--maximize { background: #28c840; }
  .qd-dot:hover { transform: scale(1.1); }
  .qd-dot--close:hover    { box-shadow: 0 0 6px rgba(255, 95, 87, 0.6); }
  .qd-dot--minimize:hover { box-shadow: 0 0 6px rgba(254, 188, 46, 0.6); }
  .qd-dot--maximize:hover { box-shadow: 0 0 6px rgba(40, 200, 64, 0.6); }
</style>
<div class="qd-traffic">
  <button class="qd-dot qd-dot--close" title="Close" onclick="pywebview.api.close()"></button>
  <button class="qd-dot qd-dot--minimize" title="Minimize" onclick="pywebview.api.minimize()"></button>
  <button class="qd-dot qd-dot--maximize" title="Fullscreen" onclick="pywebview.api.maximize()"></button>
</div>"""

_CONTROLS_HTML = "" if sys.platform == "win32" else _CONTROLS_MAC

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
