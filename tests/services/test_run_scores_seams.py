"""Seams for _run_scores: env-injected cache ceiling, no import-time env read."""
from __future__ import annotations

import quodeq.services.scoring._run_scores as run_scores


def test_resolve_cache_max_honors_injected_env():
    assert run_scores._resolve_cache_max({"QUODEQ_DEFAULT_CACHE_MAX": "7"}) == 7


def test_resolve_cache_max_defaults_without_env():
    assert run_scores._resolve_cache_max({}) == 256


def test_resolve_cache_max_ignores_garbage():
    assert run_scores._resolve_cache_max({"QUODEQ_DEFAULT_CACHE_MAX": "soon"}) == 256


def test_no_import_time_env_read():
    """The ceiling is resolved per call via the env-injection seam, not
    frozen into a module constant at import time."""
    assert not hasattr(run_scores, "_DEFAULT_CACHE_MAX")
