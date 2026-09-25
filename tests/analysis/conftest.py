"""Shared fixtures for tests/analysis."""
from __future__ import annotations

import pytest

from quodeq.analysis.provider_cache import reset_provider_config_cache
from quodeq.analysis.dispatch_policy import DispatchPolicy

from ._api_size_cap_dispatch_helpers import CAP, _TEST_PROVIDER


@pytest.fixture(autouse=True)
def _reset_provider_config_cache() -> None:
    """Reset the module-wide provider config cache before and after each test.

    ``get_provider_configs()`` lazily populates a process-lifetime cache. A
    test that points ``QUODEQ_AI_PROVIDERS_PATH`` at a fixture file and calls
    the module-level function (rather than a fresh ``_ProviderConfigCache()``
    instance) would otherwise poison every later test in the session with
    stale config data.
    """
    reset_provider_config_cache()
    yield
    reset_provider_config_cache()


@pytest.fixture
def api_config():
    """ApiRunnerConfig pointed at a local endpoint (test_api_runner* siblings)."""
    from quodeq.analysis._api_runner import ApiRunnerConfig

    return ApiRunnerConfig(
        model="test-model",
        api_base="http://localhost:8000/v1",
        api_key="test-key",
    )


def _dispatch_policy(monkeypatch, provider_type: str) -> DispatchPolicy:
    """Build a literal-provider DispatchPolicy for the given provider type.

    ``default_dispatch_policy()`` (the factory every un-injected caller —
    ``RunConfig.dispatch_policy()``, the queue worker without a RunConfig —
    resolves through) reads ``get_provider_configs()`` from inside
    ``dispatch_policy.py``'s own body. Patching it there, rather than
    patching ``default_dispatch_policy`` itself, reaches every caller
    regardless of which module imported the factory by name.
    """
    configs = {_TEST_PROVIDER: {"type": provider_type}}
    monkeypatch.setenv("QUODEQ_MAX_API_FILE_SIZE", str(CAP))
    monkeypatch.setenv("AI_CMD", _TEST_PROVIDER)
    monkeypatch.setattr("quodeq.analysis.dispatch_policy.get_provider_configs", lambda: configs)
    return DispatchPolicy(provider_configs=configs, ai_cmd=_TEST_PROVIDER, file_size_cap=CAP)


@pytest.fixture
def api_provider(monkeypatch) -> DispatchPolicy:
    """A literal API-type DispatchPolicy."""
    return _dispatch_policy(monkeypatch, "api")


@pytest.fixture
def cli_provider(monkeypatch) -> DispatchPolicy:
    """A literal CLI-type DispatchPolicy. See :func:`api_provider`."""
    return _dispatch_policy(monkeypatch, "cli")
