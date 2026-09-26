"""Orchestrates update checks. Every public entry point degrades gracefully on
the failures fetch_latest/write_state document; a genuine bug propagates."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from quodeq import __version__
from quodeq.shared.clock import utc_now_iso
from quodeq.shared.env import env_int
from quodeq.shared.env_resolve import resolve_env
from quodeq.shared.fault_isolation import run_isolated
from quodeq.update import channel as _channel
from quodeq.update import selfupdate as _selfupdate
from quodeq.update.compare import is_newer
from quodeq.update.source import fetch_latest
from quodeq.update.state import UpdateState, read_state, write_state

_logger = logging.getLogger(__name__)
_DEFAULT_INTERVAL = 86400


def _interval(env: dict[str, str]) -> int:
    return env_int("QUODEQ_UPDATE_CHECK_INTERVAL", _DEFAULT_INTERVAL, env=env, warn=False)


def should_check(state: UpdateState, env: dict[str, str] | None = None) -> bool:
    """Decide whether a network check is due.

    False when the user turned auto-check off, when QUODEQ_NO_UPDATE_NOTIFIER
    is set, or on CI. Otherwise the last attempt must be at least
    QUODEQ_UPDATE_CHECK_INTERVAL seconds old (24h by default); an unreadable
    timestamp counts as due.
    """
    environ = resolve_env(env)
    if not state.auto_check_enabled:
        return False
    if environ.get("QUODEQ_NO_UPDATE_NOTIFIER"):
        return False
    if environ.get("CI") or environ.get("CONTINUOUS_INTEGRATION"):
        return False
    if not state.last_check_ts:
        return True
    try:
        last = datetime.fromisoformat(state.last_check_ts)
        return (datetime.now(timezone.utc) - last).total_seconds() >= _interval(environ)
    except (ValueError, TypeError):
        # ValueError: unparseable. TypeError: a naive timestamp (no tzinfo)
        # makes the aware-minus-naive subtraction above raise.
        return True


def run_check(env: dict[str, str] | None = None, force: bool = False) -> None:
    """Fetch the latest release and fold it into the on-disk state.

    The attempt timestamp is stamped and persisted BEFORE the network call, so
    it survives every failure -- including one outside the narrowed except
    below -- without turning this into a per-launch retry. *force* skips the
    ``should_check`` gate. Fails soft only for the (AttributeError, TypeError)
    a malformed GitHub/PyPI JSON body leaks through ``fetch_latest``; anything
    else is a bug and propagates (``check_async``'s thread boundary is what
    isolates a direct call from a daemon thread).
    """
    state = read_state(env)
    if not force and not should_check(state, env):
        return
    # Persisted here, before the network call: the one write every launch is
    # guaranteed to get, whatever fetch_latest does or raises.
    state.last_check_ts = utc_now_iso()
    write_state(state, env)
    try:
        info = fetch_latest(_channel.detect_channel(), state.etag)
        if info is None:
            return
        if info.not_modified:
            state.etag = info.etag or state.etag
            write_state(state, env)
            return
        state.latest_version = info.version
        state.latest_url = info.url
        state.download_url = info.download_url
        state.is_security = info.is_security
        state.etag = info.etag
        write_state(state, env)
    except (AttributeError, TypeError) as exc:
        _logger.debug("update check failed: %s", exc, exc_info=True)


def check_async(env: dict[str, str] | None = None) -> None:
    """Run ``run_check`` on a daemon thread so startup is never blocked."""
    try:
        threading.Thread(
            target=lambda: run_isolated(lambda: run_check(env), label="update check", log=_logger),
            daemon=True,
        ).start()
    except RuntimeError as exc:
        _logger.warning("could not start update-check thread: %s", exc, exc_info=True)


def get_status(env: dict[str, str] | None = None) -> dict:
    """Return the update payload the UI and CLI render, read straight from state.

    ``update_available`` is False for a version the user already dismissed, and
    ``is_security`` only rides along with an available update. Reads state and
    the install channel, never the network.
    """
    state = read_state(env)
    available = is_newer(__version__, state.latest_version) and (
        state.latest_version != state.dismissed_version
    )
    return {
        "current": __version__,
        "latest": state.latest_version,
        "update_available": available,
        "is_security": state.is_security and available,
        "dismissed_version": state.dismissed_version,
        "latest_url": state.latest_url,
        "download_url": state.download_url,
        "action_command": _channel.upgrade_command(env=env),
        "channel": _channel.detect_channel(),
        "disclosed": state.disclosed,
        "auto_check_enabled": state.auto_check_enabled,
        "last_check_ts": state.last_check_ts,
        "self_update": _selfupdate.describe(state.download_url),
    }


def begin_self_update(env: dict[str, str] | None = None) -> dict:
    """Precondition-check and kick off a self-update.

    Returns ``{"ok": True, "status": ...}`` on success, or
    ``{"ok": False, "code": ..., "error": ..., "reason": ...}`` on failure
    ("reason" is present only for the UNSUPPORTED code). Never raises for
    ordinary precondition failures; the caller translates the result to HTTP.
    """
    status = get_status(env)
    self_update = status.get("self_update") or {}
    if not status.get("update_available"):
        return {"ok": False, "code": "NO_UPDATE", "error": "no update available"}
    if not self_update.get("supported"):
        return {
            "ok": False,
            "code": "UNSUPPORTED",
            "error": "self-update is not supported here",
            "reason": self_update.get("reason"),
        }
    if not _selfupdate.start(status.get("download_url"), status.get("latest")):
        return {"ok": False, "code": "BUSY", "error": "self-update already running"}
    return {"ok": True, "status": get_status(env)}


def dismiss(version: str, env: dict[str, str] | None = None) -> None:
    """Silence the notice for *version*. A later release re-opens it."""
    state = read_state(env)
    state.dismissed_version = version
    write_state(state, env)


def set_settings(
    env: dict[str, str] | None = None,
    *,
    auto_check_enabled: bool | None = None,
    disclosed: bool | None = None,
) -> None:
    """Update the auto-check and disclosure preferences. None leaves a field alone."""
    state = read_state(env)
    if auto_check_enabled is not None:
        state.auto_check_enabled = auto_check_enabled
    if disclosed is not None:
        state.disclosed = disclosed
    write_state(state, env)
