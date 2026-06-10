"""Per-run aggregate of API-runner parse drops (issue #606).

``_api_runner._parse_findings`` counts finding-shaped objects the model
emitted but validation rejected. Each call already logs that count as a
WARNING, but a systemic output-shape problem (a prompt or model change that
malformes findings across many files) drowns in thousands of per-call lines.

This module accumulates the per-call (dropped, kept) counts process-wide —
the whole run (all dimensions, all pool worker threads) executes in one
process, so a lock-guarded module counter is the aggregation seam. The
dimension loops call :func:`report_run_drop_stats` once at end of run to
log the aggregate, elevate a single warning when the drop ratio crosses
:data:`DROP_RATIO_WARN_THRESHOLD`, and emit a structured ``drop_stats``
marker for the dashboard stream (mirroring the per-dim ``cache_stats``
marker).

Deliberately stdlib-only: ``_loops`` imports this module, and must not pull
in ``_api_runner`` (which requires the ``quodeq[api]`` extra).
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

_logger = logging.getLogger(__name__)

# Elevate one run-level warning when MORE than this fraction of parsed
# findings was dropped. Strict inequality: 'crosses', not 'reaches'.
DROP_RATIO_WARN_THRESHOLD = 0.05


@dataclass(frozen=True)
class DropStats:
    """Run totals: findings the model emitted vs findings we kept."""

    dropped: int = 0
    kept: int = 0

    @property
    def parsed(self) -> int:
        """Total finding-shaped objects the model emitted this run."""
        return self.dropped + self.kept

    @property
    def ratio(self) -> float:
        """Fraction of parsed findings that was dropped (0.0 when none parsed)."""
        return self.dropped / self.parsed if self.parsed else 0.0


_lock = threading.Lock()
_dropped = 0
_kept = 0


def record(*, dropped: int, kept: int) -> None:
    """Accumulate one API call's parse counts. Thread-safe."""
    global _dropped, _kept
    with _lock:
        _dropped += dropped
        _kept += kept


def consume() -> DropStats:
    """Return the accumulated totals and reset the accumulator.

    Consume-and-reset keeps sequential runs in one process independent.
    """
    global _dropped, _kept
    with _lock:
        stats = DropStats(dropped=_dropped, kept=_kept)
        _dropped = 0
        _kept = 0
    return stats


def report_run_drop_stats() -> DropStats:
    """Log the run's aggregate drop ratio and emit the ``drop_stats`` marker.

    Silent no-op when no API calls were recorded (CLI-provider runs, or a
    run where the model emitted no finding-shaped objects at all) — there
    is no ratio to report and the marker would be noise.
    """
    stats = consume()
    if stats.parsed == 0:
        return stats
    _logger.info(
        "API runner parse summary: kept %d, dropped %d of %d parsed finding(s) "
        "(%.1f%% drop ratio)",
        stats.kept, stats.dropped, stats.parsed, stats.ratio * 100,
    )
    if stats.ratio > DROP_RATIO_WARN_THRESHOLD:
        _logger.warning(
            "API runner dropped %.1f%% of parsed findings this run (%d of %d) -- "
            "above the %.0f%% threshold. This points at a systemic output-shape "
            "problem (prompt or model change?); see the per-call drop warnings "
            "in the run log for samples.",
            stats.ratio * 100, stats.dropped, stats.parsed,
            DROP_RATIO_WARN_THRESHOLD * 100,
        )
    from quodeq.engine._runner_markers import emit_marker  # noqa: PLC0415
    emit_marker(
        "drop_stats",
        dropped=stats.dropped, kept=stats.kept, ratio=round(stats.ratio, 4),
    )
    return stats
