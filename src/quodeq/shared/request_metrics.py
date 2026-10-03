"""Request-scoped counters behind the ``Server-Timing`` header.

The perf budgets in ``tests/perf`` count evaluation.db opens and report
reads by patching ``open``. That is fine in a test and wrong in production,
so the served counterpart is explicit: the few chokepoints that open a run
database, parse a report or consult a stamp cache call ``count`` here, and
the API layer opens a scope per request and reads the totals back.

Outside a request scope every ``count`` is a no-op, so background threads
(warm-up, cache maintenance) and the CLI pay one attribute read.
"""
from __future__ import annotations

import threading
import time
from collections import Counter, deque
from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass
class RequestMetrics:
    """What one request cost, as counted at the data chokepoints."""

    started: float
    db_opens: int = 0
    report_reads: int = 0
    cache_hits: int = 0
    cache_misses: int = 0

    def elapsed_ms(self, now: float | None = None) -> float:
        """Milliseconds since the scope opened."""
        return ((time.perf_counter() if now is None else now) - self.started) * _MS_PER_S

    @property
    def cache_outcome(self) -> str:
        """``hit`` when every cache lookup hit, ``miss`` when any missed, ``none`` when none ran."""
        if self.cache_misses:
            return CACHE_MISS
        return CACHE_HIT if self.cache_hits else CACHE_NONE


_MS_PER_S = 1000.0
CACHE_HIT = "hit"
CACHE_MISS = "miss"
CACHE_NONE = "none"

_CURRENT: ContextVar[RequestMetrics | None] = ContextVar("quodeq_request_metrics", default=None)


def begin() -> Token:
    """Open a metrics scope for the current context; pair with ``end``."""
    return _CURRENT.set(RequestMetrics(started=time.perf_counter()))


def end(token: Token) -> None:
    """Close the scope opened by ``begin``."""
    _CURRENT.reset(token)


def current() -> RequestMetrics | None:
    """The open scope, or None outside a request."""
    return _CURRENT.get()


def count(field: str, n: int = 1) -> None:
    """Add *n* to *field* on the open scope; no-op outside a request."""
    metrics = _CURRENT.get()
    if metrics is not None:
        setattr(metrics, field, getattr(metrics, field) + n)


def server_timing(metrics: RequestMetrics) -> str:
    """``Server-Timing`` header value: db opens, report reads, build time, cache outcome."""
    return ", ".join((
        f'db;desc="{metrics.db_opens} opens"',
        f'reads;desc="{metrics.report_reads} reports"',
        f"build;dur={metrics.elapsed_ms():.1f}",
        f'cache;desc="{metrics.cache_outcome}"',
    ))


def log_suffix() -> str:
    """The open scope as one bracketed token for the request log line; empty outside a scope."""
    metrics = _CURRENT.get()
    if metrics is None:
        return ""
    return (
        f" [db={metrics.db_opens} reads={metrics.report_reads} "
        f"build={metrics.elapsed_ms():.0f}ms cache={metrics.cache_outcome}]"
    )


RATE_WINDOW_S = 60.0


class RequestRates:
    """Requests per route rule over the last ``RATE_WINDOW_S`` seconds."""

    def __init__(self, window_s: float = RATE_WINDOW_S) -> None:
        self._window_s = window_s
        self._events: deque[tuple[float, str]] = deque()
        self._lock = threading.Lock()

    def record(self, rule: str, now: float | None = None) -> None:
        """Note one request to *rule*."""
        stamp = time.monotonic() if now is None else now
        with self._lock:
            self._events.append((stamp, rule))
            self._prune(stamp)

    def snapshot(self, now: float | None = None) -> dict[str, int]:
        """Request counts by rule inside the window, most requested first."""
        stamp = time.monotonic() if now is None else now
        with self._lock:
            self._prune(stamp)
            counts = Counter(rule for _, rule in self._events)
        return dict(counts.most_common())

    def _prune(self, now: float) -> None:
        cutoff = now - self._window_s
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()
