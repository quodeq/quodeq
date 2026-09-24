"""Defensive env parsing: malformed values fall back instead of raising.

Covers these env sites: QUODEQ_JOB_TIMEOUT_S,
QUODEQ_CANCEL_GRACE_S (config.services_env, read lazily per call by
services._external_jobs.cancel_external_run -- no longer an import-time
module constant; see
tests/services/test_external_jobs.py::TestCancelGraceReadPerCall, which is
already grandfathered for the private ``_external_jobs`` import this needs),
QUODEQ_GIT_CLONE_TIMEOUT_S (config.clone_env, read lazily per call by
services._fs_clone and by the _cli_resolution import-time constant), and
QUODEQ_MAX_HISTORY_RUNS. Import-time constants are exercised via
importlib.reload with the env var set, then restored.
"""
from __future__ import annotations

import importlib

from quodeq.config.clone_env import git_clone_timeout_s
from quodeq.services.jobs import JobManager
from quodeq.services.scoring import max_history_runs


def _reload_attr(monkeypatch, module_name: str, var: str, value: str, attr: str):
    """Reload *module_name* with ``var=value`` set, return *attr*, then restore."""
    module = importlib.import_module(module_name)
    monkeypatch.setenv(var, value)
    try:
        importlib.reload(module)
        return getattr(module, attr)
    finally:
        monkeypatch.delenv(var, raising=False)
        importlib.reload(module)


class TestJobTimeoutCap:
    def test_invalid_value_falls_back_to_no_cap(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_JOB_TIMEOUT_S", "abc")
        assert JobManager()._job_timeout_cap_s == 0.0

    def test_negative_value_falls_back_to_no_cap(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_JOB_TIMEOUT_S", "-5")
        assert JobManager()._job_timeout_cap_s == 0.0

    def test_valid_value_is_used(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_JOB_TIMEOUT_S", "120")
        assert JobManager()._job_timeout_cap_s == 120.0


class TestMaxHistoryRuns:
    def test_invalid_value_falls_back(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_MAX_HISTORY_RUNS", "lots")
        assert max_history_runs() == 100

    def test_zero_falls_back(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_MAX_HISTORY_RUNS", "0")
        assert max_history_runs() == 100

    def test_valid_value_is_used(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_MAX_HISTORY_RUNS", "7")
        assert max_history_runs() == 7


class TestImportTimeConstants:
    def test_clone_timeout_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_GIT_CLONE_TIMEOUT_S", "fast")
        assert git_clone_timeout_s() == 300

    def test_fetch_timeout_invalid_falls_back(self, monkeypatch):
        value = _reload_attr(
            monkeypatch, "quodeq._cli_resolution",
            "QUODEQ_GIT_CLONE_TIMEOUT_S", "fast", "FETCH_TIMEOUT_S",
        )
        assert value == 300
