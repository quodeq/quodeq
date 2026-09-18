"""Per-run aggregate of API-runner parse drops (issue #606).

``_api_schema._parse_findings`` counts finding-shaped objects the model
emitted but validation rejected. Each call already logs that count as a
WARNING, but a systemic output-shape problem (a prompt or model change that
malformes findings across many files) drowns in thousands of per-call lines.

This module accumulates the per-call (dropped, kept) counts in a
:class:`DropStatsCounter` — the whole run (all dimensions, all pool worker
threads) executes in one process, so the module-default instance is the
aggregation seam. The dimension loops call :func:`report_run_drop_stats`
once at end of run to log the aggregate, elevate a single warning when the
drop ratio crosses :data:`DROP_RATIO_WARN_THRESHOLD`, and emit a structured
``drop_stats`` marker for the dashboard stream (mirroring the per-dim
``cache_stats`` marker).

Deliberately stdlib-only: ``_loops`` imports this module, and must not pull
in ``_api_runner`` (which requires the ``quodeq[api]`` extra).
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field

_logger = logging.getLogger(__name__)

# Elevate one run-level warning when MORE than this fraction of parsed
# findings was dropped. Strict inequality: 'crosses', not 'reaches'.
DROP_RATIO_WARN_THRESHOLD = 0.05

# How many distinct drop reasons to name in a log line. The histogram has a
# long tail of one-off model slips; the leading few are what identify a
# systemic output-shape problem.
_TOP_REASONS = 5


def format_reasons(reasons: Mapping[str, int], limit: int = _TOP_REASONS) -> str:
    """Render a drop-reason histogram as ``field:error_type xN``, commonest first.

    Ties break on the key so the line is stable across runs. Returns
    ``"reason not recorded"`` for an empty histogram rather than an empty
    string, so a log line that interpolates it never trails off mid-sentence.
    """
    ranked = sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))
    if not ranked:
        return "reason not recorded"
    return ", ".join(f"{key} x{count}" for key, count in ranked[:limit])


@dataclass(frozen=True)
class DropStats:
    """Run totals: findings the model emitted vs findings we kept."""

    dropped: int = 0
    kept: int = 0
    reasons: Mapping[str, int] = field(default_factory=dict)

    @property
    def parsed(self) -> int:
        """Total finding-shaped objects the model emitted this run."""
        return self.dropped + self.kept

    @property
    def ratio(self) -> float:
        """Fraction of parsed findings that was dropped (0.0 when none parsed)."""
        return self.dropped / self.parsed if self.parsed else 0.0

    def top_reasons(self, limit: int = _TOP_REASONS) -> str:
        """Render the commonest drop reasons as ``field:error_type xN``."""
        return format_reasons(self.reasons, limit)


class DropStatsCounter:
    """Lock-guarded (dropped, kept) accumulator with consume-and-reset reads.

    Instantiable so tests (or any future concurrent-run host) get isolated
    counts; production shares the module-default instance below.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._dropped = 0
        self._kept = 0
        self._reasons: dict[str, int] = {}

    def record(
        self, *, dropped: int, kept: int, reasons: Mapping[str, int] | None = None,
    ) -> None:
        """Accumulate one API call's parse counts. Thread-safe.

        *reasons* is the call's ``field:error_type`` histogram from
        ``_api_schema._parse_findings``; it folds into the run-wide tally so
        the end-of-run summary can name which constraint did the rejecting.
        """
        with self._lock:
            self._dropped += dropped
            self._kept += kept
            for key, count in (reasons or {}).items():
                self._reasons[key] = self._reasons.get(key, 0) + count

    def consume(self) -> DropStats:
        """Return the accumulated totals and reset the accumulator.

        Consume-and-reset keeps sequential runs in one process independent.
        """
        with self._lock:
            stats = DropStats(
                dropped=self._dropped, kept=self._kept, reasons=dict(self._reasons),
            )
            self._dropped = 0
            self._kept = 0
            self._reasons = {}
        return stats


_default_counter = DropStatsCounter()


def record(
    *, dropped: int, kept: int, reasons: Mapping[str, int] | None = None,
) -> None:
    """Accumulate one API call's parse counts on the run-wide default counter."""
    _default_counter.record(dropped=dropped, kept=kept, reasons=reasons)


def consume() -> DropStats:
    """Consume-and-reset the run-wide default counter."""
    return _default_counter.consume()


def report_run_drop_stats(counter: DropStatsCounter | None = None) -> DropStats:
    """Log the run's aggregate drop ratio and emit the ``drop_stats`` marker.

    Reads (and resets) *counter*, defaulting to the run-wide module counter.
    Silent no-op when no API calls were recorded (CLI-provider runs, or a
    run where the model emitted no finding-shaped objects at all) — there
    is no ratio to report and the marker would be noise.
    """
    stats = (counter or _default_counter).consume()
    if stats.parsed == 0:
        return stats
    _logger.info(
        "API runner parse summary: kept %d, dropped %d of %d parsed finding(s) "
        "(%.1f%% drop ratio)%s",
        stats.kept, stats.dropped, stats.parsed, stats.ratio * 100,
        f"; top reasons: {stats.top_reasons()}" if stats.reasons else "",
    )
    if stats.ratio > DROP_RATIO_WARN_THRESHOLD:
        _logger.warning(
            "API runner dropped %.1f%% of parsed findings this run (%d of %d) -- "
            "above the %.0f%% threshold. This points at a systemic output-shape "
            "problem (prompt or model change?). Rejecting constraints, commonest "
            "first: %s.",
            stats.ratio * 100, stats.dropped, stats.parsed,
            DROP_RATIO_WARN_THRESHOLD * 100, stats.top_reasons(),
        )
    from quodeq.analysis._runner_markers import emit_marker  # noqa: PLC0415
    emit_marker(
        "drop_stats",
        dropped=stats.dropped, kept=stats.kept, ratio=round(stats.ratio, 4),
    )
    return stats
