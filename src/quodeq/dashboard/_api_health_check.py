"""Health-check and polling helpers for the action API."""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request

from quodeq.shared.logging import log_info

_HEALTH_CHECK_TIMEOUT_S = 0.5
_HEALTH_POLL_INTERVAL_S = 0.2
_DEFAULT_WAIT_TIMEOUT_S = 10
_MAX_HEALTH_POLL_ATTEMPTS = 200
_MAX_JITTER_DELAY_S = 2.0


def action_api_healthy(base_url: str) -> bool:
    """Return True if the action API at *base_url* responds healthy."""
    url = f"{base_url}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=_HEALTH_CHECK_TIMEOUT_S) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("ok") is True
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
        return False


def wait_for_action_api(base_url: str, timeout_s: float = _DEFAULT_WAIT_TIMEOUT_S) -> None:
    """Block until the action API becomes healthy, or raise TimeoutError."""
    log_info(f"Waiting for Action API at {base_url}...")
    start = time.monotonic()
    attempts = 0
    delay = _HEALTH_POLL_INTERVAL_S
    max_delay = _MAX_JITTER_DELAY_S
    while time.monotonic() - start < timeout_s and attempts < _MAX_HEALTH_POLL_ATTEMPTS:
        if action_api_healthy(base_url):
            return None
        attempts += 1
        if attempts % 10 == 0:
            elapsed = round(time.monotonic() - start, 1)
            log_info(f"Still waiting for Action API ({elapsed:.0f}s elapsed)...")
        jitter = random.uniform(0, delay * 0.2)
        time.sleep(delay + jitter)
        delay = min(delay * 1.5, max_delay)
    raise TimeoutError(f"Action API did not become ready within {timeout_s} seconds.")
