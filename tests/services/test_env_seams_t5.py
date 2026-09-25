"""Service-layer env seams: an injected mapping is the only source read.

Each seam is checked twice -- with a value injected, and with an injected
``{}`` while the process environment carries a different value, which must
be ignored (`os.environ if env is None else env`, never `env or ...`).
"""
from __future__ import annotations

import pytest

from quodeq.services._dashboard_cache import DEFAULT_RUN_DIM_CACHE_MAX, run_dim_cache_max
from quodeq.services._dashboard_history import DEFAULT_MAX_HISTORY_RUNS, max_history_runs
from quodeq.services._job_file_store import _default_persist_dir
from quodeq.services.accumulated import acc_dim_cache_max, walk_cache_max
from quodeq.services.plugin_discovery import _DEFAULT_PLUGIN_CACHE_TTL, _PluginCache, _plugin_cache_ttl
from quodeq.services.scoring._run_scores import _FALLBACK_CACHE_MAX, _resolve_cache_max
from quodeq.services.shared_settings import shared_settings_path


class TestRunDimCacheMax:
    def test_uses_the_injected_value(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_RUN_DIM_CACHE_MAX", "7")
        assert run_dim_cache_max(env={"QUODEQ_RUN_DIM_CACHE_MAX": "13"}) == 13

    def test_empty_injected_env_ignores_the_process(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_RUN_DIM_CACHE_MAX", "7")
        assert run_dim_cache_max(env={}) == DEFAULT_RUN_DIM_CACHE_MAX

    @pytest.mark.parametrize("bad_value", ["abc", "-5"])
    def test_falls_back_to_default_on_invalid_value(self, bad_value):
        assert run_dim_cache_max(env={"QUODEQ_RUN_DIM_CACHE_MAX": bad_value}) == DEFAULT_RUN_DIM_CACHE_MAX

    def test_zero_is_a_valid_value(self):
        assert run_dim_cache_max(env={"QUODEQ_RUN_DIM_CACHE_MAX": "0"}) == 0

    def test_honours_a_valid_value(self):
        assert run_dim_cache_max(env={"QUODEQ_RUN_DIM_CACHE_MAX": "250"}) == 250


class TestAccDimCacheMax:
    """QUODEQ_ACC_CACHE_MAX; 0 is a valid size (evicts every entry immediately,
    see services/cache.py's ``_cache_store``), so only non-numeric and
    negative values fall back to the default."""

    @pytest.mark.parametrize("bad_value", ["abc", "-5"])
    def test_falls_back_to_default_on_invalid_value(self, bad_value):
        assert acc_dim_cache_max(env={"QUODEQ_ACC_CACHE_MAX": bad_value}) == 256

    def test_zero_is_a_valid_value(self):
        assert acc_dim_cache_max(env={"QUODEQ_ACC_CACHE_MAX": "0"}) == 0

    def test_honours_a_valid_value(self):
        assert acc_dim_cache_max(env={"QUODEQ_ACC_CACHE_MAX": "250"}) == 250


class TestWalkCacheMax:
    """QUODEQ_ACC_WALK_CACHE_MAX=0 is documented to disable the walk cache
    entirely, so 0 must stay a valid (non-fallback) value."""

    @pytest.mark.parametrize("bad_value", ["abc", "-5"])
    def test_falls_back_to_default_on_invalid_value(self, bad_value):
        assert walk_cache_max(env={"QUODEQ_ACC_WALK_CACHE_MAX": bad_value}) == 2048

    def test_zero_disables_the_cache(self):
        assert walk_cache_max(env={"QUODEQ_ACC_WALK_CACHE_MAX": "0"}) == 0

    def test_honours_a_valid_value(self):
        assert walk_cache_max(env={"QUODEQ_ACC_WALK_CACHE_MAX": "250"}) == 250


class TestMaxHistoryRuns:
    def test_uses_the_injected_value(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_MAX_HISTORY_RUNS", "7")
        assert max_history_runs(env={"QUODEQ_MAX_HISTORY_RUNS": "13"}) == 13

    def test_empty_injected_env_ignores_the_process(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_MAX_HISTORY_RUNS", "7")
        assert max_history_runs(env={}) == DEFAULT_MAX_HISTORY_RUNS


class TestJobPersistDir:
    def test_uses_the_injected_value(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_JOB_PERSIST_DIR", str(tmp_path / "from-process"))
        injected = tmp_path / "from-env"
        assert _default_persist_dir(env={"QUODEQ_JOB_PERSIST_DIR": str(injected)}) == injected

    def test_empty_injected_env_ignores_the_process(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_JOB_PERSIST_DIR", str(tmp_path / "from-process"))
        assert _default_persist_dir(env={}) != tmp_path / "from-process"


class TestPluginCacheTtl:
    def test_uses_the_injected_value(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_PLUGIN_CACHE_TTL", "5")
        assert _plugin_cache_ttl({"QUODEQ_PLUGIN_CACHE_TTL": "11"}) == 11

    def test_empty_injected_env_ignores_the_process(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_PLUGIN_CACHE_TTL", "5")
        assert _plugin_cache_ttl({}) == _DEFAULT_PLUGIN_CACHE_TTL

    def test_cache_takes_the_ttl_from_its_injected_env(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_PLUGIN_CACHE_TTL", "5")
        assert _PluginCache(env={"QUODEQ_PLUGIN_CACHE_TTL": "11"})._ttl == 11

    def test_cache_with_empty_injected_env_ignores_the_process(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_PLUGIN_CACHE_TTL", "5")
        assert _PluginCache(env={})._ttl == _DEFAULT_PLUGIN_CACHE_TTL


class TestResolveCacheMax:
    def test_uses_the_injected_value(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_DEFAULT_CACHE_MAX", "5")
        assert _resolve_cache_max({"QUODEQ_DEFAULT_CACHE_MAX": "11"}) == 11

    def test_empty_injected_env_ignores_the_process(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_DEFAULT_CACHE_MAX", "5")
        assert _resolve_cache_max({}) == _FALLBACK_CACHE_MAX


class TestSharedSettingsPath:
    def test_uses_the_injected_value(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_DIR", str(tmp_path / "from-process"))
        injected = tmp_path / "from-env"
        assert shared_settings_path(env={"QUODEQ_DIR": str(injected)}).parent == injected

    def test_empty_injected_env_ignores_the_process(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_DIR", str(tmp_path / "from-process"))
        assert shared_settings_path(env={}).parent != tmp_path / "from-process"
