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
"""
from __future__ import annotations

import threading
from collections.abc import Callable

from quodeq.analysis._types import AnalysisOptions

# How often the watcher thread persists in-flight cache entries during
# dispatch. Smaller = less work lost on cancel; larger = less I/O during
# normal runs. 30s is a pragmatic default -- at typical model dispatch
# speeds (~10-30s per file), each tick covers a handful of completed files.
_PERSIST_INTERVAL_S = 30.0


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
    and never kill the watcher. Final persist happens on stop signal so
    the watcher's last-known state is also written to cache.
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
