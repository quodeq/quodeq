"""Injectable collaborator seams for the dashboard's API-startup path.

``ApiProbes`` bundles the low-level networking/health/spawn calls that
``_server.py``'s API-startup functions make (port checks, health checks,
host allowlisting, and the local-process spawn). ``DashboardHooks`` bundles
the runner-level lifecycle steps ``run_dashboard`` composes (killing a
stale API, the ensure-API step as a whole, building the UI, checking dev
prerequisites).

Both are frozen dataclasses whose fields default to the production
collaborator of the same name, so existing callers passing neither see no
change. Tests construct one with fakes instead of patching this package's
module attributes.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from quodeq.dashboard._api_health_check import action_api_healthy
from quodeq.dashboard._build import maybe_build_ui
from quodeq.dashboard._networking import _is_port_open, _local_hosts
from quodeq.dashboard._process import _kill_stale_action_api, _spawn_and_wait_local
from quodeq.shared.prereqs import check_dashboard_dev_prereqs

if TYPE_CHECKING:
    import subprocess

    from quodeq.dashboard._api_health import ApiConfig


@dataclass(frozen=True)
class ApiProbes:
    """Injectable seam for ``_server.py``'s API-startup collaborators."""

    is_port_open: Callable[[str, int], bool] = _is_port_open
    api_healthy: Callable[[str], bool] = action_api_healthy
    local_hosts: Callable[..., frozenset[str]] = _local_hosts
    kill_stale: Callable[[str, int], None] = _kill_stale_action_api
    spawn: Callable[[int, str, "ApiConfig | None"], tuple[str, "subprocess.Popen"]] = _spawn_and_wait_local


@dataclass(frozen=True)
class DashboardHooks:
    """Injectable seam for ``runner.py``'s launch-lifecycle steps.

    ``ensure_api`` defaults to ``None`` rather than ``_start_action_api``
    to avoid a circular import (``runner.py`` imports this module); ``None``
    resolves to ``_start_action_api`` at the ``run_dashboard`` call site.
    """

    kill_stale: Callable[[str, int], None] = _kill_stale_action_api
    ensure_api: Callable[..., tuple[str, "subprocess.Popen | None"]] | None = None
    build_ui: Callable[..., Path] = maybe_build_ui
    check_prereqs: Callable[[], None] = check_dashboard_dev_prereqs
