"""Health-check and polling helpers for the action API."""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from http import HTTPStatus

from quodeq.shared.logging import log_info
from quodeq.shared.quiet_run import Spinner

_HEALTH_CHECK_TIMEOUT_S = 0.5
_HEALTH_POLL_INTERVAL_S = 0.2
# Generous: the first start after an install or upgrade compiles every module,
# and on Windows real-time AV scans each new file first, which can take well
# over 10s. A child that dies stops the wait early (see *alive*).
_DEFAULT_WAIT_TIMEOUT_S = 60
_MAX_HEALTH_POLL_ATTEMPTS = 200
_MAX_JITTER_DELAY_S = 2.0
_LOG_CADENCE = 10
_JITTER_RATIO = 0.2
_BACKOFF_MULTIPLIER = 1.5


def action_api_healthy(base_url: str) -> bool:
    """Return True if the action API at *base_url* responds healthy."""
    url = f"{base_url}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=_HEALTH_CHECK_TIMEOUT_S) as response:
            if response.status != HTTPStatus.OK:
                return False
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("ok") is True
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
        return False


def wait_for_action_api(
    base_url: str, timeout_s: float = _DEFAULT_WAIT_TIMEOUT_S,
    alive: Callable[[], bool] | None = None,
) -> None:
    """Block until the action API becomes healthy, or raise TimeoutError.

    *alive*, when given, reports whether the API process is still running;
    once it says no, waiting longer is pointless and this raises at once.

    On a terminal a spinner shows the wait; elsewhere (logs, pipes) it is
    plain log lines.
    """
    with Spinner("Starting the Action API") as spinner:
        if not spinner.animating:
            log_info(f"Waiting for Action API at {base_url}...")
        start = time.monotonic()
        attempts = 0
        delay = _HEALTH_POLL_INTERVAL_S
        max_delay = _MAX_JITTER_DELAY_S
        while time.monotonic() - start < timeout_s and attempts < _MAX_HEALTH_POLL_ATTEMPTS:
            if action_api_healthy(base_url):
                return None
            if alive is not None and not alive():
                raise TimeoutError("Action API exited before it became ready.")
            attempts += 1
            if attempts % _LOG_CADENCE == 0 and not spinner.animating:
                elapsed = round(time.monotonic() - start, 1)
                log_info(f"Still waiting for Action API ({elapsed:.0f}s elapsed)...")
            jitter = random.uniform(0, delay * _JITTER_RATIO)
            spinner.sleep(delay + jitter)
            delay = min(delay * _BACKOFF_MULTIPLIER, max_delay)
    raise TimeoutError(f"Action API did not become ready within {timeout_s} seconds.")
