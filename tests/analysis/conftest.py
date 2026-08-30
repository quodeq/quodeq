"""Shared fixtures for tests/analysis."""
from __future__ import annotations

import pytest

from quodeq.analysis._provider_cache import reset_provider_config_cache


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
