"""Defensive env parsing: malformed values fall back instead of raising.

Covers the P2 fix round's env sites: QUODEQ_JOB_TIMEOUT_S,
QUODEQ_CANCEL_GRACE_S, QUODEQ_GIT_CLONE_TIMEOUT_S (services._fs_clone and
_cli_resolution), and QUODEQ_MAX_HISTORY_RUNS. Import-time constants are
exercised via importlib.reload with the env var set, then restored.
"""
from __future__ import annotations

import importlib

from quodeq.services.jobs import JobManager
from quodeq.services.scoring import _max_history_runs


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
        assert _max_history_runs() == 100

    def test_zero_falls_back(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_MAX_HISTORY_RUNS", "0")
        assert _max_history_runs() == 100

    def test_valid_value_is_used(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_MAX_HISTORY_RUNS", "7")
        assert _max_history_runs() == 7


class TestImportTimeConstants:
    def test_cancel_grace_invalid_falls_back(self, monkeypatch):
        value = _reload_attr(
            monkeypatch, "quodeq.services._external_jobs",
            "QUODEQ_CANCEL_GRACE_S", "abc", "_DEFAULT_GRACE_PERIOD_S",
        )
        assert value == 30.0

    def test_clone_timeout_invalid_falls_back(self, monkeypatch):
        value = _reload_attr(
            monkeypatch, "quodeq.services._fs_clone",
            "QUODEQ_GIT_CLONE_TIMEOUT_S", "fast", "_GIT_CLONE_TIMEOUT_S",
        )
        assert value == 300

    def test_fetch_timeout_invalid_falls_back(self, monkeypatch):
        value = _reload_attr(
            monkeypatch, "quodeq._cli_resolution",
            "QUODEQ_GIT_CLONE_TIMEOUT_S", "fast", "_FETCH_TIMEOUT_S",
        )
        assert value == 300
