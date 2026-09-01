"""Dim-state I/O and process-level guards shared by the dimension loops."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from quodeq.analysis._types import RunConfig
from quodeq.analysis.errors import FatalProviderError
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.shared import cancellation
from quodeq.data.fs.dimensions_state_store import DimState, write_dim_state, IllegalDimTransitionError


def _safe_write_dim_state(
    run_dir: Path | None, dim: str, state: DimState, *,
    reason: str | None = None, exit_reason: str | None = None,
    log: LogSink = NULL_LOG,
) -> None:
    """Best-effort dim-state write. Never raises into the loop.

    Tests that mock RunConfig don't have a real work_dir, and we don't
    want state I/O failures to crash the loop. Logged at WARNING for
    visibility. Lifecycle errors (illegal transition) are also swallowed:
    if the state machine rejects the transition, that's a bug we want to
    see in logs but not crash on.
    """
    if run_dir is None:
        return
    try:
        run_dir = Path(run_dir)
    except (TypeError, ValueError):
        return
    try:
        write_dim_state(run_dir, dim, state, reason=reason, exit_reason=exit_reason)
    except IllegalDimTransitionError as exc:
        log.warning(f"[loop] dim-state transition rejected: {exc}")
    except (OSError, AttributeError, TypeError) as exc:
        log.warning(f"[loop] dim-state write failed for {dim}: {exc}")


def _run_dir_for(config: RunConfig) -> Path | None:
    """Resolve the run directory for ``dimensions.json`` writes.

    Returns ``config.run_dir`` when set -- the canonical anchor populated by
    the CLI/API entry point. The lifecycle context seeds ``dimensions.json``
    at this same path, so loop transitions and lifecycle seed agree.

    Falls back to ``work_dir`` / ``src`` for tests and any caller that
    hasn't been migrated to populate ``run_dir``. Backward-compat: in pre-
    fix code paths, ``work_dir`` was the evidence subdir, which caused the
    loop to write a parallel ``dimensions.json`` the API never read. New
    callers should always populate ``run_dir`` explicitly.

    Only accepts a real ``Path`` or ``str``. Mocked configs (whose fields
    are ``MagicMock`` instances) return ``None`` so tests don't create
    stray ``<MagicMock id=...>`` directories in the CWD.
    """
    for attr in ("run_dir", "work_dir", "src"):
        candidate = getattr(config, attr, None)
        if isinstance(candidate, (str, Path)):
            try:
                return Path(candidate)
            except (TypeError, ValueError):
                continue
    return None


def _interruption_reason(exc: BaseException | None = None) -> str:
    """Map a process state and optional exception to a dim-state reason.

    - Fatal provider error (quota/auth/billing): 'provider_fatal'.
    - Circuit-breaker trip: returns 'circuit_breaker' (recognised so the
      lifecycle exit handler can map to exit_reason=failure_streak).
    - Cancellation flag set: the recorded cancel cause ('provider_fatal',
      'agent_failure_streak') when there is one, else 'cancelled_signal'.
    - Otherwise: 'failed_exception'.
    """
    from quodeq.analysis.cache._failure_streak import CircuitBreakerError
    if isinstance(exc, FatalProviderError):
        return "provider_fatal"
    if isinstance(exc, CircuitBreakerError):
        return "circuit_breaker"
    if cancellation.is_cancelled():
        reason = cancellation.cancel_reason() or ""
        if reason.startswith("provider_fatal"):
            return "provider_fatal"
        if reason == "agent_failure_streak":
            return "agent_failure_streak"
        return "cancelled_signal"
    return "failed_exception"


def _silence_broken_stdout() -> None:
    """Redirect stdout/stderr to /dev/null after a BrokenPipeError.

    Once the parent has closed its end of the pipe every subsequent write to
    stdout/stderr raises BrokenPipeError. The actual analysis work (evidence
    files, MCP calls, etc.) doesn't depend on those streams - only logging
    does. Swapping the streams to /dev/null lets remaining dimensions run.
    """
    try:
        devnull = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115 - long-lived
        sys.stdout = devnull
        sys.stderr = devnull
    except OSError:
        pass
