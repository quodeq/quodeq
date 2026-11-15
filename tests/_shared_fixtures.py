"""The fixtures every test gets, gathered so ``conftest.py`` registers them with one import.

Each lives in its own module with its reasoning. Importing a fixture into
``conftest.py`` is what registers it, and it must be registered there: the
environment guard in ``conftest.py`` has to wrap these fixtures, which it
only does when they share its scope.
"""
from __future__ import annotations

from tests._cwd_guard import _cwd_leak_guard
from tests._offline_dns import _offline_dns
from tests._session_client import _session_test_client
from tests._windows_launch import (
    _windows_launch_rules,
    argv_as_written,
    installed_cli,
    windows_system_tools,
)

__all__ = [
    "_cwd_leak_guard",
    "_offline_dns",
    "_session_test_client",
    "_windows_launch_rules",
    "argv_as_written",
    "installed_cli",
    "windows_system_tools",
]
