"""Background watcher that periodically persists in-flight cache entries.

Split out of ``dimension_runner.py`` (B4/B5e): the watcher thread body and
the failure-streak threshold resolution are self-contained pieces of the
V2 cache-aware dimension processor. The thread itself is still constructed
in ``dimension_runner.py`` -- ``mock.patch("...dimension_runner.threading")``
resolves where ``threading.Thread``/``threading.Event()`` are called, not
where this module happens to live.

``_periodic_persist`` takes a ``log_warning`` callable rather than owning
its own logger, so this module has no logging import of its own -- the
caller threads its module logger's ``.warning`` method through.

``_make_persist_fn`` builds the callable the thread runs. It binds the
dispatch-constant provenance hashes and one ``DispatchJsonlState``. Ticks
read the JSONL incrementally through that state; the final persist (once
``stop_event`` is set) resets it first and re-reads the whole file.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.analysis.cache._jsonl_state import DispatchJsonlState
from quodeq.analysis.cache._key_provenance import _hash_prompts_combined
from quodeq.analysis.cache.backend import CacheBackend
from quodeq.analysis.cache.dimension_helpers import ClassifyResult, persist_dispatch_results
from quodeq.analysis.fingerprint import _hash_standards, dimension_params_state

# How often the watcher thread persists in-flight cache entries during
# dispatch. Smaller = less work lost on cancel; larger = less I/O during
# normal runs. 30s is a pragmatic default -- at typical model dispatch
# speeds (~10-30s per file), each tick covers a handful of completed files.
_PERSIST_INTERVAL_S = 30.0


def _compute_persist_hash_inputs(config: RunConfig, dimension: str) -> dict:
    """Provenance hash inputs for persist_dispatch_results, as kwargs.

    standards_dir/prompts_dir/dimension are constant for a whole dispatch,
    so the caller computes these once (at watcher start) instead of
    persist_dispatch_results recomputing them on every tick.
    """
    standards_hash = (
        _hash_standards(config.standards_dir, dimension, config.src)
        if config.standards_dir else ""
    ) or ""
    params_hash, effective_params = dimension_params_state(
        config.standards_dir, dimension, config.src,
    )
    return {
        "standards_hash": standards_hash, "params_hash": params_hash,
        "effective_params": effective_params,
        "prompts_hash": _hash_prompts_combined(config.prompts_dir),
    }


def _make_persist_fn(
    config: RunConfig, dim_id: str, jsonl: Path, classify: ClassifyResult,
    cache: CacheBackend, stop_event: threading.Event,
) -> Callable[[], None]:
    """Build the watcher's persist callable for one dispatch.

    One ``DispatchJsonlState`` for the whole dispatch means each tick reads
    only the JSONL lines appended since the previous call and rewrites only
    the files those lines touched, instead of re-parsing and re-putting
    everything every interval.

    The final persist, the call made after *stop_event* is set, does not
    trust that state: the pool rewrites the JSONL in place (dedup) before
    the watcher is joined, and ``LocalFileBackend.put`` swallows OSError, so
    a tick may have cleared ``dirty`` for a file whose entry never landed.
    Resetting first marks every ok file dirty again, so the final persist
    re-puts all of them, as the pre-incremental one did.
    """
    hash_inputs = _compute_persist_hash_inputs(config, dim_id)
    state = DispatchJsonlState()

    def _persist_now() -> None:
        if stop_event.is_set():
            state.reset()
        persist_dispatch_results(
            config, dim_id, miss_files=classify.misses, cache=cache,
            jsonl_path=jsonl, miss_keys=classify.miss_keys, state=state, **hash_inputs,
        )

    return _persist_now


def _resolve_failure_streak_threshold(
    opts: AnalysisOptions, *, override: int | None = None,
) -> int:
    """Return the effective breaker threshold.

    Priority: *override* (when given) > options field. 0 disables; negative
    values clamp to 0.
    """
    if override is not None:
        return max(0, override)
    return max(0, opts.failure_streak_threshold)


def _periodic_persist(
    stop_event: threading.Event, persist_fn: Callable[[], None],
    interval: float, log_warning: Callable[..., None],
) -> None:
    """Background thread: call persist_fn() until stop_event is set.

    Each tick is best-effort -- exceptions never propagate to the caller
    and never kill the watcher. Final persist happens on stop signal;
    persist_fn sees the event set and re-reads the JSONL in full.
    """
    while not stop_event.wait(timeout=interval):
        try:
            persist_fn()
        except Exception as exc:  # noqa: BLE001 — never kill the dispatch
            log_warning("incremental cache persist failed: %s", exc)
    # Final persist after stop signaled (e.g. dispatch finished or raised).
    try:
        persist_fn()
    except Exception as exc:  # noqa: BLE001
        log_warning("final cache persist failed: %s", exc)
