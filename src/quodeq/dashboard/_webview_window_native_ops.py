"""Operational helpers extracted from the facade purely to fit the file-size
cap: WindowApi's HTTP/native-dialog bodies, the reload-socket handler, and
process teardown. None of this is patch-tested by name — tests patch
urllib.request.urlopen directly (a global module attribute, patching the
real shared module rather than a name in some namespace) and the underlying
ww.webbrowser / ww.sys module objects, which work regardless of which file
calls them — so none of it needs to stay co-located with a caller in the
facade. See _webview_window.py's module docstring for what DOES need to
stay there.
"""
from __future__ import annotations

import http.client
import json
import logging
import os
import shutil
import signal
import sys
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

import webview

from quodeq.shared.constants import LOCALHOST, PLATFORM_WIN32, SCHEME_HTTP, SCHEME_HTTPS

_logger = logging.getLogger(__name__)

_EVAL_CHECK_TIMEOUT_S = 0.5
_CANCEL_TIMEOUT_S = 5.0
_DOWNLOAD_TIMEOUT_S = 120
_LOOPBACK_IPV4 = "127.0.0.1"  # loopback address a reload URL may target
_LOOPBACK_IPV6 = "::1"  # loopback address (IPv6) a reload URL may target
_SAFE_RELOAD_SCHEMES = frozenset({SCHEME_HTTP, SCHEME_HTTPS})  # is_safe_reload_url's allowed schemes
_SAFE_RELOAD_HOSTS = frozenset({LOCALHOST, _LOOPBACK_IPV4, _LOOPBACK_IPV6})  # is_safe_reload_url's allowed hosts
_PARTIAL_SUFFIX = ".part"  # suffix on the uniquely-named temp file a download streams into


def fetch_running_evaluation(base_url: str) -> dict | None:
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
    except (OSError, ValueError):
        return None
    return job if isinstance(job, dict) else None


def send_cancel_evaluation(base_url: str, job_id: str | None) -> None:
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
    except (OSError, http.client.HTTPException):
        _logger.warning("cancel-on-quit for job %s failed", job_id, exc_info=True)


def _ask_save_path(window: object, filename: str) -> str | None:
    """Open a native Save dialog defaulting to *filename*; the chosen path or None.

    None when the user cancels, or when the dialog answers with nothing
    usable. The file-type filter is derived from *filename*'s extension.
    """
    ext = filename.rsplit('.', 1)[-1] if '.' in filename else '*'
    result = window.create_file_dialog(
        webview.SAVE_DIALOG,
        save_filename=filename,
        file_types=(f'{ext.upper()} files (*.{ext})', 'All files (*.*)'),
    )
    if not result:
        return None
    path = result if isinstance(result, str) else result[0] if result else None
    return path or None


def save_via_dialog(window: object, content: str, filename: str) -> bool:
    """Open a native Save dialog and write content to the chosen path."""
    if not window:
        return False
    path = _ask_save_path(window, filename)
    if not path:
        return False
    try:
        Path(path).write_text(content, encoding='utf-8')
        return True
    except OSError as exc:
        _logger.warning("save to %s failed: %s", path, exc, exc_info=True)
        return False


def download_via_dialog(window: object, base_url: str, path: str, filename: str) -> bool:
    """Fetch a URL from the API and save it via native Save dialog."""
    if not window or not base_url:
        return False
    save_path = _ask_save_path(window, filename)
    if not save_path:
        return False
    try:
        url = urllib.parse.urljoin(base_url, path)
        if not is_safe_reload_url(url):
            return False
        _stream_to(url, Path(save_path))
        return True
    except (OSError, ValueError, http.client.HTTPException):
        # OSError: connection/URLError/write failures. ValueError: a URL
        # urllib cannot parse. HTTPException: a truncated or malformed
        # response body (IncompleteRead), which is not an OSError. All three
        # are "download failed" to the user; anything else is a bug and
        # propagates to the js_api bridge.
        return False


def _stream_to(url: str, target: Path) -> None:
    """Stream *url* into *target* in fixed-size chunks.

    The body lands in a uniquely named temp file in *target*'s directory
    (``tempfile.mkstemp``, so it can never collide with a file that already
    exists there) and replaces *target* only once complete, so a failed
    download never truncates a file the user chose to overwrite. Cleanup
    only ever removes the temp file this call created, never a pre-existing
    file of the user's, even one that happens to end in ``.part``.
    """
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f"{target.name}.", suffix=_PARTIAL_SUFFIX)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT_S) as resp:
            shutil.copyfileobj(resp, out)
        os.replace(tmp_path, target)
    finally:
        tmp_path.unlink(missing_ok=True)


def kill_api(pid: int) -> None:
    """Terminate the Flask API process."""
    try:
        sig = signal.SIGTERM if sys.platform != PLATFORM_WIN32 else signal.CTRL_BREAK_EVENT
        os.kill(pid, sig)
    except (OSError, ProcessLookupError) as exc:
        _logger.debug("action API process already gone or not killable: %s", exc)


def is_safe_reload_url(url: str) -> bool:
    """Return True only when *url* points to the local dashboard origin.

    Rejects anything that is not http/https on 127.0.0.1, localhost, or ::1
    so a rogue local process cannot navigate the privileged webview to an
    arbitrary URL via the reload socket.
    """
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in _SAFE_RELOAD_SCHEMES and parsed.hostname in _SAFE_RELOAD_HOSTS


def _current_url(window: object) -> str | None:
    """The window's own URL, or None if the backend won't say.

    Only used to reload in place, so an unavailable URL just means "raise the
    window without refreshing" — never a reason to fail the focus request.
    """
    try:
        url = window.get_current_url()  # type: ignore[union-attr]
    except (webview.errors.WebViewException, AttributeError, RuntimeError):
        # Backend-specific; the window may be mid-teardown. An unavailable
        # URL just means "raise the window without refreshing".
        _logger.debug("get_current_url failed; focusing without reload", exc_info=True)
        return None
    return url if isinstance(url, str) and is_safe_reload_url(url) else None


def make_on_reload(window: object) -> "Callable[[str], None]":
    """Return the ``_on_reload`` handler bound to *window*.

    Extracted from ``main()`` so the test suite can import and exercise the
    real implementation rather than a hand-rolled duplicate.

    An empty URL is the "focus" case a plain relaunch sends (see
    InstanceController.send_focus): stay on the page this window already has,
    reloading it in place so a ``--dev`` relaunch picks up the rebuilt UI, and
    raise the window either way.
    """
    def _on_reload(new_url: str) -> None:
        if new_url and not is_safe_reload_url(new_url):
            _logger.warning("Ignoring unsafe reload URL: %s", new_url)
            return
        target = new_url or _current_url(window)
        if target:
            window.load_url(target)  # type: ignore[union-attr]
        window.on_top = True  # type: ignore[union-attr]
        window.on_top = False  # type: ignore[union-attr]

    return _on_reload
