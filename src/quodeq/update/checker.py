"""Orchestrates update checks. Every public entry point is fail-silent."""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone

from quodeq import __version__
from quodeq.update import channel as _channel
from quodeq.update.compare import is_newer
from quodeq.update.source import fetch_latest
from quodeq.update.state import UpdateState, read_state, write_state

_logger = logging.getLogger(__name__)
_DEFAULT_INTERVAL = 86400


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _interval(env: dict[str, str]) -> int:
    try:
        return int(env.get("QUODEQ_UPDATE_CHECK_INTERVAL", _DEFAULT_INTERVAL))
    except ValueError:
        return _DEFAULT_INTERVAL


def should_check(state: UpdateState, env: dict[str, str] | None = None) -> bool:
    environ = env if env is not None else os.environ
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
    except ValueError:
        return True


def run_check(env: dict[str, str] | None = None, force: bool = False) -> None:
    try:
        state = read_state(env)
        if not force and not should_check(state, env):
            return
        # Stamp the attempt time before the network call so it persists even on failure.
        state.last_check_ts = _now_iso()
        try:
            info = fetch_latest(_channel.detect_channel(), state.etag)
            if info is None:
                write_state(state, env)
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
        except Exception:
            _logger.debug("update check failed", exc_info=True)
            write_state(state, env)  # always persist last_check_ts
    except Exception:  # pragma: no cover - outer blanket guard
        _logger.debug("run_check failed", exc_info=True)


def check_async(env: dict[str, str] | None = None) -> None:
    try:
        threading.Thread(target=run_check, args=(env,), daemon=True).start()
    except Exception:  # pragma: no cover
        _logger.debug("could not start update-check thread", exc_info=True)


def get_status(env: dict[str, str] | None = None) -> dict:
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
    }


def dismiss(version: str, env: dict[str, str] | None = None) -> None:
    state = read_state(env)
    state.dismissed_version = version
    write_state(state, env)


def set_settings(
    env: dict[str, str] | None = None,
    *,
    auto_check_enabled: bool | None = None,
    disclosed: bool | None = None,
) -> None:
    state = read_state(env)
    if auto_check_enabled is not None:
        state.auto_check_enabled = auto_check_enabled
    if disclosed is not None:
        state.disclosed = disclosed
    write_state(state, env)
