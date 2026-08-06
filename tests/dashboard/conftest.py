"""Shared isolation for the dashboard suite.

Every test here runs against a throwaway QUODEQ_RUN_DIR. Without it, any
code path that resolves the default run dir (InstanceController's
dashboard.sock, the action-API PID file) reaches into the developer's real
~/.quodeq/run — probing, focusing, or killing whatever quodeq instance is
live on the machine. That is exactly how running this suite next to an open
dashboard popped its window to the front and failed
test_run_dashboard_native_window: the relaunch hand-off probed the real
socket, found the live instance, and handed the test's launch off to it.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_run_dir(tmp_path_factory, monkeypatch):
    run_dir = tmp_path_factory.mktemp("quodeq-run")
    monkeypatch.setenv("QUODEQ_RUN_DIR", str(run_dir))
    return run_dir
