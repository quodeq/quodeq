"""Env-dependent configuration resolves per call, not at import time.

Four settings were frozen into module constants when their module was first
imported, so a test (or a runtime settings change) could only move them via
importlib.reload — the workaround tests/services/test_env_fallbacks.py still
carries. They now resolve lazily through the codebase's env-injection seam
(``env: dict | None = None``).
"""
from __future__ import annotations


class TestAnalysisConfigDefaults:
    def test_max_turns_reads_env_at_construction(self, monkeypatch):
        from quodeq.analysis._config import AnalysisConfig

        monkeypatch.setenv("QUODEQ_DEFAULT_MAX_TURNS", "42")
        assert AnalysisConfig().max_turns == 42

    def test_max_duration_reads_env_at_construction(self, monkeypatch):
        from quodeq.analysis._config import AnalysisConfig

        monkeypatch.setenv("QUODEQ_DEFAULT_MAX_DURATION", "77")
        assert AnalysisConfig().max_duration == 77

    def test_defaults_without_env(self, monkeypatch):
        from quodeq.analysis._config import AnalysisConfig

        monkeypatch.delenv("QUODEQ_DEFAULT_MAX_TURNS", raising=False)
        monkeypatch.delenv("QUODEQ_DEFAULT_MAX_DURATION", raising=False)
        cfg = AnalysisConfig()
        assert (cfg.max_turns, cfg.max_duration) == (200, 1800)

    def test_malformed_env_falls_back(self, monkeypatch):
        from quodeq.analysis._config import AnalysisConfig

        monkeypatch.setenv("QUODEQ_DEFAULT_MAX_TURNS", "not-a-number")
        assert AnalysisConfig().max_turns == 200


class TestProvidersPath:
    def test_analysis_reuses_the_shared_resolver(self):
        """One lazy resolver for QUODEQ_AI_PROVIDERS_PATH, not two."""
        from quodeq.analysis import _provider_cache
        from quodeq.shared.provider_env import _providers_path

        assert _provider_cache._providers_path is _providers_path
        assert not hasattr(_provider_cache, "_AI_PROVIDERS_PATH")

    def test_env_override_is_seen_without_reload(self, monkeypatch, tmp_path):
        from quodeq.shared.provider_env import _providers_path

        target = tmp_path / "providers.json"
        monkeypatch.setenv("QUODEQ_AI_PROVIDERS_PATH", str(target))
        assert _providers_path() == target


class TestNonScoutProviders:
    def test_reads_env_at_call_time(self, monkeypatch):
        from quodeq.analysis.subagents._pool_launcher import _non_scout_providers

        monkeypatch.setenv("QUODEQ_NON_SCOUT_PROVIDERS", "alpha,beta")
        assert _non_scout_providers() == ("alpha", "beta")

    def test_default_when_unset(self, monkeypatch):
        from quodeq.analysis.subagents._pool_launcher import _non_scout_providers

        monkeypatch.delenv("QUODEQ_NON_SCOUT_PROVIDERS", raising=False)
        assert _non_scout_providers() == ("codex", "gemini")

    def test_injected_env_wins(self):
        from quodeq.analysis.subagents._pool_launcher import _non_scout_providers

        assert _non_scout_providers({"QUODEQ_NON_SCOUT_PROVIDERS": "solo"}) == ("solo",)


class TestPluginCacheTtl:
    def test_reads_env_at_construction(self, monkeypatch):
        from quodeq.services.plugin_discovery import _PluginCache

        monkeypatch.setenv("QUODEQ_PLUGIN_CACHE_TTL", "5")
        assert _PluginCache()._ttl == 5

    def test_default_and_malformed_fall_back(self, monkeypatch):
        from quodeq.services.plugin_discovery import _PluginCache

        monkeypatch.setenv("QUODEQ_PLUGIN_CACHE_TTL", "soon")
        assert _PluginCache()._ttl == 60
        monkeypatch.delenv("QUODEQ_PLUGIN_CACHE_TTL", raising=False)
        assert _PluginCache()._ttl == 60

    def test_explicit_ttl_still_wins(self, monkeypatch):
        from quodeq.services.plugin_discovery import _PluginCache

        monkeypatch.setenv("QUODEQ_PLUGIN_CACHE_TTL", "5")
        assert _PluginCache(ttl=99)._ttl == 99


class TestCallTimeEnvSeams:
    """Readers that already resolved per call gain the injection parameter."""

    def test_api_file_size_cap(self):
        from quodeq.analysis.dispatch_policy import api_file_size_cap

        assert api_file_size_cap(env={"QUODEQ_MAX_API_FILE_SIZE": "123"}) == 123

    def test_agent_failure_streak_limit(self):
        from quodeq.analysis.subagents._pool_scaling import _agent_failure_streak_limit

        assert _agent_failure_streak_limit(env={"QUODEQ_AGENT_FAILURE_STREAK": "7"}) == 7

    def test_mcp_max_batch(self):
        from quodeq.analysis.mcp.handlers import _max_file_batch_size

        assert _max_file_batch_size(env={"QUODEQ_MCP_MAX_BATCH": "9"}) == 9

    def test_online_cache_root(self, tmp_path):
        from quodeq.context.online_cache import cache_root

        assert cache_root(env={"QUODEQ_CACHE_ROOT": str(tmp_path)}) == tmp_path / "online"
