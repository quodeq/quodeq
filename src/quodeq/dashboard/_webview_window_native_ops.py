"""Operational helpers extracted from the facade purely to fit the file-size
cap: _WindowApi's HTTP/native-dialog bodies, the reload-socket handler, and
process teardown. None of this is patch-tested by name — tests patch the
underlying ww.urllib.request / ww.webbrowser / ww.sys module objects, which
work regardless of which file calls them (patch.object(ww.urllib.request,
...) patches the real shared module, not a name in ww's own namespace) — so
none of it needs to stay co-located with a caller in the facade. See
_webview_window.py's module docstring for what DOES need to stay there.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

import webview

_logger = logging.getLogger(__name__)

_EVAL_CHECK_TIMEOUT_S = 0.5
_CANCEL_TIMEOUT_S = 5.0
_DOWNLOAD_TIMEOUT_S = 120


def _fetch_running_evaluation(base_url: str) -> dict | None:
    """Return the first non-stale running evaluation job, or None.

    The staleness rule (a "running" record whose project no longer exists is
    ignored) lives in the API — see GET /api/evaluations/active and
    services.active_evaluation. This shell only performs the request and a
    shape check.
    """
    if not base_url:
        return None
    try:
        req = urllib.request.Request(f"{base_url}/api/evaluations/active")
        with urllib.request.urlopen(req, timeout=_EVAL_CHECK_TIMEOUT_S) as resp:
            job = json.loads(resp.read())
    except Exception:
        return None
    return job if isinstance(job, dict) else None


def _send_cancel_evaluation(base_url: str, job_id: str | None) -> None:
    """Issue DELETE /api/evaluations/<job_id> to stop a running scan.

    The API enforces an Origin header to reject cross-site requests, so set
    it explicitly to the dashboard base URL; without it the call 403s and
    silently no-ops. Best-effort: any failure is swallowed so a close is
    never blocked by a failed cancel, but logged so it's diagnosable.
    """
    if not job_id or not base_url:
        return
    try:
        req = urllib.request.Request(
            f"{base_url}/api/evaluations/{urllib.parse.quote(job_id)}",
            method="DELETE",
            headers={"Origin": base_url},
        )
        # Give the API time to SIGTERM the scan and respond; the 0.5s used
        # for the eval-check poll is too tight here.
        with urllib.request.urlopen(req, timeout=_CANCEL_TIMEOUT_S):
            pass
    except Exception:
        _logger.warning("cancel-on-quit for job %s failed", job_id, exc_info=True)


def _save_via_dialog(window: object, content: str, filename: str) -> bool:
    """Open a native Save dialog and write content to the chosen path."""
    if not window:
        return False
    ext = filename.rsplit('.', 1)[-1] if '.' in filename else '*'
    result = window.create_file_dialog(
        webview.SAVE_DIALOG,
        save_filename=filename,
        file_types=(f'{ext.upper()} files (*.{ext})', 'All files (*.*)'),
    )
    if not result:
        return False
    path = result if isinstance(result, str) else result[0] if result else None
    if not path:
        return False
    try:
        Path(path).write_text(content, encoding='utf-8')
        return True
    except OSError:
        return False


def _download_via_dialog(window: object, base_url: str, path: str, filename: str) -> bool:
    """Fetch a URL from the API and save it via native Save dialog."""
    if not window or not base_url:
        return False
    ext = filename.rsplit('.', 1)[-1] if '.' in filename else '*'
    result = window.create_file_dialog(
        webview.SAVE_DIALOG,
        save_filename=filename,
        file_types=(f'{ext.upper()} files (*.{ext})', 'All files (*.*)'),
    )
    if not result:
        return False
    save_path = result if isinstance(result, str) else result[0] if result else None
    if not save_path:
        return False
    try:
        url = base_url + path
        with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT_S) as resp:
            Path(save_path).write_bytes(resp.read())
        return True
    except (OSError, Exception):
        return False


def _kill_api(pid: int) -> None:
    """Terminate the Flask API process."""
    try:
        sig = signal.SIGTERM if sys.platform != "win32" else signal.CTRL_BREAK_EVENT
        os.kill(pid, sig)
    except (OSError, ProcessLookupError):
        pass


def _is_safe_reload_url(url: str) -> bool:
    """Return True only when *url* points to the local dashboard origin.

    Rejects anything that is not http/https on 127.0.0.1, localhost, or ::1
    so a rogue local process cannot navigate the privileged webview to an
    arbitrary URL via the reload socket.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and parsed.hostname in {
        "127.0.0.1",
        "localhost",
        "::1",
    }


def _current_url(window: object) -> str | None:
    """The window's own URL, or None if the backend won't say.

    Only used to reload in place, so an unavailable URL just means "raise the
    window without refreshing" — never a reason to fail the focus request.
    """
    try:
        url = window.get_current_url()  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 — backend-specific; the window may be mid-teardown
        _logger.debug("get_current_url failed; focusing without reload", exc_info=True)
        return None
    return url if isinstance(url, str) and _is_safe_reload_url(url) else None


def _make_on_reload(window: object) -> "Callable[[str], None]":
    """Return the ``_on_reload`` handler bound to *window*.

    Extracted from ``main()`` so the test suite can import and exercise the
    real implementation rather than a hand-rolled duplicate.

    An empty URL is the "focus" case a plain relaunch sends (see
    InstanceController.send_focus): stay on the page this window already has,
    reloading it in place so a ``--dev`` relaunch picks up the rebuilt UI, and
    raise the window either way.
    """
    def _on_reload(new_url: str) -> None:
        if new_url and not _is_safe_reload_url(new_url):
            _logger.warning("Ignoring unsafe reload URL: %s", new_url)
            return
        target = new_url or _current_url(window)
        if target:
            window.load_url(target)  # type: ignore[union-attr]
        window.on_top = True  # type: ignore[union-attr]
        window.on_top = False  # type: ignore[union-attr]

    return _on_reload
