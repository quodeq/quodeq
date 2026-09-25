"""Accessors in config/services_env.py own the raw env read/parse for the
services layer's env-tuned limits; behavior (default, parse rule) mirrors
exactly what each service module used to do inline before this seam."""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.config import services_env
from quodeq.shared.env import get_index_db_path


@pytest.mark.parametrize("resolver, var, default", [
    (services_env.run_dim_cache_max, "QUODEQ_RUN_DIM_CACHE_MAX", 256),
    (services_env.max_history_runs, "QUODEQ_MAX_HISTORY_RUNS", 100),
    (services_env.max_concurrent_jobs, "QUODEQ_MAX_CONCURRENT_JOBS", 8),
    (services_env.max_violation_files, "QUODEQ_MAX_VIOLATION_FILES", 20),
])
class TestIntResolvers:
    def test_unset_reads_as_default(self, resolver, var, default):
        assert resolver(env={}) == default

    def test_valid_value_parses(self, resolver, var, default):
        assert resolver(env={var: "42"}) == 42

    def test_invalid_value_falls_back_to_default(self, resolver, var, default):
        assert resolver(env={var: "not-a-number"}) == default

    def test_explicit_env_wins_over_os_environ(self, resolver, var, default, monkeypatch):
        monkeypatch.setenv(var, "7")
        assert resolver(env={var: "13"}) == 13
        assert resolver(env={}) == default  # injected {} ignores the process


class TestRunDimCacheMax:
    """0 is a valid explicit size (no minimum clamp), unlike the others below."""

    def test_zero_is_a_real_value(self):
        assert services_env.run_dim_cache_max(env={"QUODEQ_RUN_DIM_CACHE_MAX": "0"}) == 0


class TestMaxHistoryRuns:
    def test_zero_falls_back_to_default(self):
        assert services_env.max_history_runs(env={"QUODEQ_MAX_HISTORY_RUNS": "0"}) == 100


class TestMaxConcurrentJobs:
    def test_zero_falls_back_to_default(self):
        assert services_env.max_concurrent_jobs(env={"QUODEQ_MAX_CONCURRENT_JOBS": "0"}) == 8

    def test_negative_falls_back_to_default(self):
        assert services_env.max_concurrent_jobs(env={"QUODEQ_MAX_CONCURRENT_JOBS": "-1"}) == 8


class TestMaxViolationFiles:
    """No minimum clamp (matches the pre-existing behavior): 0 and negative
    values pass through unchanged, only a non-numeric value falls back."""

    def test_zero_passes_through(self):
        assert services_env.max_violation_files(env={"QUODEQ_MAX_VIOLATION_FILES": "0"}) == 0

    def test_negative_passes_through(self):
        assert services_env.max_violation_files(env={"QUODEQ_MAX_VIOLATION_FILES": "-3"}) == -3


class TestCancelGraceS:
    def test_unset_reads_as_default(self):
        assert services_env.cancel_grace_s(env={}) == 30.0

    def test_valid_value_parses(self):
        assert services_env.cancel_grace_s(env={"QUODEQ_CANCEL_GRACE_S": "5.5"}) == 5.5

    def test_invalid_value_falls_back_to_default(self):
        assert services_env.cancel_grace_s(env={"QUODEQ_CANCEL_GRACE_S": "abc"}) == 30.0

    def test_negative_falls_back_to_default(self):
        assert services_env.cancel_grace_s(env={"QUODEQ_CANCEL_GRACE_S": "-1"}) == 30.0

    def test_explicit_env_wins_over_os_environ(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_CANCEL_GRACE_S", "7")
        assert services_env.cancel_grace_s(env={"QUODEQ_CANCEL_GRACE_S": "13"}) == 13.0
        assert services_env.cancel_grace_s(env={}) == 30.0


class TestJobTimeoutCapS:
    def test_unset_reads_as_default(self):
        assert services_env.job_timeout_cap_s(env={}) == 0.0

    def test_valid_value_parses(self):
        assert services_env.job_timeout_cap_s(env={"QUODEQ_JOB_TIMEOUT_S": "120"}) == 120.0

    def test_invalid_value_falls_back_to_default(self):
        assert services_env.job_timeout_cap_s(env={"QUODEQ_JOB_TIMEOUT_S": "abc"}) == 0.0

    def test_negative_falls_back_to_default(self):
        assert services_env.job_timeout_cap_s(env={"QUODEQ_JOB_TIMEOUT_S": "-5"}) == 0.0

    def test_explicit_env_wins_over_os_environ(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_JOB_TIMEOUT_S", "7")
        assert services_env.job_timeout_cap_s(env={"QUODEQ_JOB_TIMEOUT_S": "13"}) == 13.0
        assert services_env.job_timeout_cap_s(env={}) == 0.0


class TestJobPersistDir:
    def test_unset_falls_back_to_the_index_db_sibling(self):
        expected = Path(get_index_db_path()).parent / "run" / "jobs"
        assert services_env.job_persist_dir(env={}) == expected

    def test_explicit_value_is_used(self, tmp_path):
        injected = tmp_path / "from-env"
        assert services_env.job_persist_dir(env={"QUODEQ_JOB_PERSIST_DIR": str(injected)}) == injected

    def test_explicit_env_wins_over_os_environ(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_JOB_PERSIST_DIR", str(tmp_path / "from-process"))
        injected = tmp_path / "from-env"
        assert services_env.job_persist_dir(
            env={"QUODEQ_JOB_PERSIST_DIR": str(injected)}) == injected
        assert services_env.job_persist_dir(env={}) != tmp_path / "from-process"
