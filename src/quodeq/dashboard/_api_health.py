"""Action API spawning and health-check helpers.

This module is the public entry point; implementation is split across
``_api_health_check`` (health polling) and ``_api_spawn`` (process management).
"""
from __future__ import annotations

# Re-exports so existing importers keep working
from quodeq.dashboard._api_health_check import (  # noqa: F401
    action_api_healthy,
    wait_for_action_api,
)
from quodeq.dashboard._api_spawn import (  # noqa: F401
    ApiConfig,
    spawn_action_api,
    spawn_and_wait,
)
