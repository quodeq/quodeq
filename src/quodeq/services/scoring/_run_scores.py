"""Read scored dimensions for a single run from disk, with an LRU cache."""
from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

from quodeq.core.types import DimensionResult
from quodeq.services._cache import DimensionCacheContext, make_lru_dimension_fetcher
from quodeq.shared._env_resolve import resolve_env

_FALLBACK_CACHE_MAX = 256

# Module-level cache shared across callers in the same process. Quodeq's
# server is single-process, so this is intentional. Multi-process setups
# can inject their own ``cache``/``cache_lock`` to bypass shared state.
_cache: OrderedDict[tuple, list[DimensionResult]] = OrderedDict()
_cache_lock = threading.Lock()


def _resolve_cache_max(env: dict[str, str] | None = None) -> int:
    """LRU ceiling from QUODEQ_DEFAULT_CACHE_MAX, resolved per call.

    Env-injection seam (not an import-time constant) so tests and callers
    can vary the ceiling without reloading the module.
    """
    raw = resolve_env(env).get("QUODEQ_DEFAULT_CACHE_MAX", "")
    return int(raw) if raw.isdigit() and int(raw) > 0 else _FALLBACK_CACHE_MAX


def get_run_dimensions(
    reports_root: Path, project: str, run_id: str,
    *, ctx: DimensionCacheContext | None = None,
    env: dict[str, str] | None = None,
) -> list[DimensionResult]:
    """Return dimension data for a single run, using the shared LRU cache.

    *ctx* replaces the module-level cache, lock and ceiling with the caller's
    own; without it the ceiling comes from ``QUODEQ_DEFAULT_CACHE_MAX`` in
    *env* (``os.environ`` when None).
    """
    if ctx is None:
        ctx = DimensionCacheContext(cache=_cache, lock=_cache_lock, max_size=_resolve_cache_max(env))
    fetcher = make_lru_dimension_fetcher(reports_root, project, ctx)
    return fetcher(run_id)
