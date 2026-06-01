"""Dimension loop orchestrators - run dimensions sequentially or incrementally."""
from __future__ import annotations

import json
import os
import sys
import time
from copy import copy
from dataclasses import replace
from collections.abc import Callable
from pathlib import Path

from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis.dimension_runner import DimensionRunner, _log_dimension_result
from quodeq.analysis.errors import EvaluationError
from quodeq.core.evidence.model import Evidence
from quodeq.engine._runner_markers import emit_marker
# NOTE: logging in inner layer - tracked for middleware extraction
from quodeq.shared.logging import log_info, log_warning
from quodeq.shared import cancellation
from quodeq.shared.dimensions_state import DimState, write_dim_state, IllegalDimTransitionError


def _safe_write_dim_state(
    run_dir: Path | None, dim: str, state: DimState, *,
    reason: str | None = None, exit_reason: str | None = None,
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
        log_warning(f"[loop] dim-state transition rejected: {exc}")
    except (OSError, AttributeError, TypeError) as exc:
        log_warning(f"[loop] dim-state write failed for {dim}: {exc}")


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

    - Circuit-breaker trip: returns 'circuit_breaker' (recognised so the
      lifecycle exit handler can map to exit_reason=failure_streak).
    - Cancellation flag set (signal or breaker-via-flag): 'cancelled_signal'.
    - Otherwise: 'failed_exception'.
    """
    from quodeq.analysis.cache._failure_streak import CircuitBreakerError
    if isinstance(exc, CircuitBreakerError):
        return "circuit_breaker"
    return "cancelled_signal" if cancellation.is_cancelled() else "failed_exception"


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


def check_zero_findings(
    result: dict[str, Evidence], source_file_count: int, skipped_count: int = 0,
    *, incremental_filter_active: bool = False,
) -> None:
    """Raise EvaluationError if all dimensions produced zero findings.

    When *incremental_filter_active* is True, zero findings is a legitimate
    outcome (PR-diff / incremental mode deliberately narrows the scan to a
    changed-file set that may contain none of the dimension's language) -
    skip the check. Otherwise a genuinely empty result is almost always a
    symptom of a broken AI CLI tool loop, not a clean codebase.
    """
    if not result or source_file_count <= 0 or incremental_filter_active:
        return
    if _count_findings(result) == 0:
        skip_msg = f" ({skipped_count} skipped)" if skipped_count else ""
        raise EvaluationError(
            f"Evaluation produced 0 findings across {len(result)} dimensions{skip_msg}. "
            f"This usually means the AI CLI could not read files or report findings "
            "- check tool permissions and MCP configuration."
        )


def _count_findings(result: dict[str, Evidence]) -> int:
    """Total violations + compliance findings across all dimension Evidence.

    Counts findings carried forward from cache as well as freshly produced
    ones -- both land in ``Evidence.principles`` for the dims in ``result``.
    """
    return sum(
        sum(len(pe.violations) + len(pe.compliance) for pe in ev.principles.values())
        for ev in result.values()
    )


def _tally_markers(jsonl_path: Path) -> tuple[int, int]:
    """Return ``(ok_count, error_count)`` from a dim's evidence JSONL.

    Counts each file once by its *latest* ``file_done`` marker status, matching
    the cache's ok_files semantics (a file that errored then re-succeeded counts
    as ok). Unreadable/missing files contribute nothing.
    """
    last_status: dict[str, str] = {}
    try:
        # errors="replace" so a corrupt (non-UTF8) evidence file degrades to
        # unparseable lines (dropped by the json.loads guard) instead of
        # raising UnicodeDecodeError out of an otherwise-successful run.
        with jsonl_path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if entry.get("_marker") != "file_done":
                    continue
                file = entry.get("file")
                status = entry.get("status")
                if isinstance(file, str) and status in ("ok", "error"):
                    last_status[file] = status
    except (FileNotFoundError, OSError):
        return 0, 0
    ok = sum(1 for s in last_status.values() if s == "ok")
    err = sum(1 for s in last_status.values() if s == "error")
    return ok, err


def check_model_reachable(run_dir: Path | None, result: dict) -> None:
    """Raise EvaluationError if the run attempted analysis but produced nothing.

    Fires only when ALL of the following hold, so it flags a genuinely worthless
    run (an unreachable/misconfigured model) without false-positiving on healthy
    or partial runs:

    - the run produced zero findings (fresh OR carried forward from cache). Any
      finding means real output exists, so a mostly-cached run is not failed just
      because the model blipped on the uncached remainder. (A lossy call now
      writes ``error`` markers, so the dim yields an *empty* Evidence rather than
      being skipped -- hence we gate on findings, not on ``result`` emptiness.)
    - zero files were successfully analysed (no ``ok`` file_done markers); and
    - at least one file was dispatched and failed (an ``error`` marker exists).

    Runs in every mode, including diff (review) and incremental (nightly) where
    ``check_zero_findings`` is deliberately bypassed -- those are exactly the
    modes where an unreachable model used to exit 0 (green) while producing
    nothing. A legitimately empty scan (no applicable files dispatched -> no
    markers) does not raise.

    Coverage note: the guard keys off file_done ``error`` markers. The Ollama /
    API provider path writes those on a lossy call (``run_api_analysis``), so the
    Ollama-backed CI flows are covered. A CLI provider (claude/gemini/codex) that
    is itself unreachable never connects to the MCP server and writes no markers
    at all, so this guard cannot see that failure in diff/incremental mode --
    that remains a known gap, out of scope for the Ollama incident this targets.
    """
    if run_dir is None or _count_findings(result) > 0:
        return
    evidence_dir = run_dir / "evidence"
    if not evidence_dir.is_dir():
        return
    ok_total = 0
    err_total = 0
    for jsonl in evidence_dir.glob("*_evidence.jsonl"):
        ok, err = _tally_markers(jsonl)
        ok_total += ok
        err_total += err
    if ok_total == 0 and err_total > 0:
        raise EvaluationError(
            f"Model produced no analysis: all {err_total} dispatched file(s) failed "
            f"and 0 were analysed. The model is likely unreachable or misconfigured "
            f"(check the provider/model name and that the server is running, "
            f"e.g. `ollama list`), or every dispatched file errored during analysis."
        )


def run_incremental_loop(
    config: RunConfig, dimensions: list[str], ctx: _AnalysisContext,
    *, runner: DimensionRunner,
    on_dimension_done: Callable[[str, Evidence], None] | None = None,
) -> dict[str, Evidence]:
    """Run incremental per-dimension analysis.

    Args:
        config: Run configuration for this evaluation.
        dimensions: Dimension identifiers to analyze.
        ctx: Shared analysis context (total count, etc.).
        runner: DimensionRunner used to analyze each dimension. The loop calls
            ``runner.run(config, dim, idx, ctx, emit_log=False)`` for the
            incremental path (the loop emits its own ``analyzing`` marker
            with "(incremental)" suffix), then calls ``_log_dimension_result``
            after a successful dim. The full-scan fallback uses
            ``emit_log=True`` so the runner emits its own analyzing marker.
    """
    result: dict[str, Evidence] = {}
    log_info(f"[loop] incremental: {len(dimensions)} dim(s) to process: {', '.join(dimensions)}")
    for idx, dimension in enumerate(dimensions, 1):
        log_info(f"[loop] entering iteration {idx}/{ctx.total} for {dimension}")
        deadline = getattr(config.options, "deadline_at", None)
        if deadline is not None and time.monotonic() >= deadline:
            log_info(f"[loop] deadline reached -- skipping {dimension} and remaining dims")
            break
        run_dir = _run_dir_for(config)
        _safe_write_dim_state(run_dir, dimension, DimState.RUNNING)
        emit_marker("analyzing", dimension=dimension)
        log_info(f"-> [{idx}/{ctx.total}] Analyzing {dimension} (incremental)")
        ev: Evidence | None = None
        last_exc: BaseException | None = None
        try:
            ev = runner.run(config, dimension, idx, ctx, emit_log=False)
        except BrokenPipeError as exc:
            _silence_broken_stdout()
            last_exc = exc
            ev = None
        except (OSError, KeyError, ValueError, RuntimeError) as exc:
            log_warning(f"[{idx}/{ctx.total}] {dimension} - incremental failed: {exc}, falling back to full")
            last_exc = exc
            fallback_options = copy(config.options)
            fallback_options.incremental_file_filter = None
            fallback_config = replace(config, options=fallback_options)
            try:
                ev = runner.run(fallback_config, dimension, idx, ctx, emit_log=True)
            except BrokenPipeError as inner_exc:
                _silence_broken_stdout()
                last_exc = inner_exc
                ev = None
            except Exception as inner_exc:  # noqa: BLE001
                last_exc = inner_exc
                ev = None
        except Exception as exc:  # noqa: BLE001
            # Loop-level diagnostic: an unanticipated exception class would
            # otherwise propagate up silently and the lifecycle would treat
            # it as failed without saying which dim. Log + swallow + continue
            # so subsequent dims still run; the surfaced log line gives us
            # the trail we need next time this happens.
            log_warning(
                f"[loop] {dimension} - unexpected exception "
                f"{type(exc).__name__}: {exc} - skipping dim, continuing loop",
            )
            last_exc = exc
            ev = None
        # on_dimension_done is caller-provided (e.g., the dashboard's
        # scoring callback). Wrap it too - an exception in a callback
        # shouldn't drop the next iteration on the floor.
        if ev:
            _safe_write_dim_state(
                run_dir, dimension, DimState.DONE,
                exit_reason=ev.exit_reason,
            )
            try:
                _log_dimension_result(ev, dimension, idx, ctx.total)
                result[dimension] = ev
                if on_dimension_done:
                    on_dimension_done(dimension, ev)
            except BrokenPipeError:
                # Stdout pipe to parent died mid-callback. Silence stdout/
                # stderr, then retry the callback once: scoring callbacks like
                # ``_score_dimension`` write evaluation/<dim>.json to disk and
                # are idempotent (overwrite). The previous "result kept"
                # message was misleading - only the in-memory Evidence stayed,
                # the persistent file write was lost with the exception.
                _silence_broken_stdout()
                result.setdefault(dimension, ev)
                if on_dimension_done:
                    try:
                        on_dimension_done(dimension, ev)
                        log_warning(
                            f"[loop] {dimension} - callback broken pipe, "
                            f"retried after silencing stdout, result persisted",
                        )
                    except Exception as exc:  # noqa: BLE001
                        log_warning(
                            f"[loop] {dimension} - callback retry after broken pipe raised "
                            f"{type(exc).__name__}: {exc} - result NOT persisted, continuing loop",
                        )
                else:
                    log_warning(f"[loop] {dimension} - callback broken pipe, no retry needed, continuing loop")
            except Exception as exc:  # noqa: BLE001
                log_warning(
                    f"[loop] {dimension} - callback raised "
                    f"{type(exc).__name__}: {exc} - result kept, continuing loop",
                )
                result.setdefault(dimension, ev)
        else:
            _safe_write_dim_state(run_dir, dimension, DimState.INCOMPLETE, reason=_interruption_reason(last_exc))
        log_info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (ev={'set' if ev else 'None'})")
    log_info(
        f"[loop] incremental finished: processed {len(result)} of {len(dimensions)} dim(s) "
        f"({', '.join(result) if result else 'none'})",
    )
    check_zero_findings(
        result, config.source_file_count,
        incremental_filter_active=config.options.incremental_file_filter is not None
            or config.options.skip_scoring,
    )
    check_model_reachable(_run_dir_for(config), result)
    return result


def run_per_dimension_loop(
    config: RunConfig, dimensions: list[str], ctx: _AnalysisContext,
    *, runner: DimensionRunner,
    on_dimension_done: Callable[[str, Evidence], None] | None = None,
) -> dict[str, Evidence]:
    """Per-dimension loop (fallback or single-dimension).

    Args:
        config: Run configuration for this evaluation.
        dimensions: Dimension identifiers to analyze.
        ctx: Shared analysis context (total count, etc.).
        runner: DimensionRunner used to analyze each dimension. The loop calls
            ``runner.run(config, dim, idx, ctx, emit_log=True)`` so the runner
            emits its own analyzing/scoring markers and success log.
    """
    result: dict[str, Evidence] = {}
    skipped_count = 0
    log_info(f"[loop] per-dimension: {len(dimensions)} dim(s) to process: {', '.join(dimensions)}")
    for idx, dimension in enumerate(dimensions, 1):
        log_info(f"[loop] entering iteration {idx}/{ctx.total} for {dimension}")
        deadline = getattr(config.options, "deadline_at", None)
        if deadline is not None and time.monotonic() >= deadline:
            log_info(f"[loop] deadline reached -- skipping {dimension} and remaining dims")
            # Remaining dims stay in PENDING (they were never RUNNING). No write needed.
            break
        run_dir = _run_dir_for(config)
        _safe_write_dim_state(run_dir, dimension, DimState.RUNNING)
        ev: Evidence | None = None
        try:
            ev = runner.run(config, dimension, idx, ctx, emit_log=True)
        except BrokenPipeError as exc:
            _silence_broken_stdout()
            skipped_count += 1
            _safe_write_dim_state(run_dir, dimension, DimState.INCOMPLETE, reason=_interruption_reason(exc))
            log_info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (skipped: broken pipe)")
            continue
        except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
            log_warning(f"[{idx}/{ctx.total}] {dimension} - failed: {exc}")
            skipped_count += 1
            _safe_write_dim_state(run_dir, dimension, DimState.INCOMPLETE, reason=_interruption_reason(exc))
            log_info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (skipped: {type(exc).__name__})")
            continue
        except Exception as exc:  # noqa: BLE001
            # Don't let an exotic exception class drop the rest of the loop
            # silently. Log + count as skipped + continue so we get the trail.
            log_warning(
                f"[loop] {dimension} - unexpected exception "
                f"{type(exc).__name__}: {exc} - skipping dim, continuing loop",
            )
            skipped_count += 1
            _safe_write_dim_state(run_dir, dimension, DimState.INCOMPLETE, reason=_interruption_reason(exc))
            log_info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (skipped: unexpected)")
            continue
        if ev is None:
            skipped_count += 1
            _safe_write_dim_state(run_dir, dimension, DimState.INCOMPLETE, reason=_interruption_reason())
            log_info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (skipped: ev=None)")
            continue
        # ev is set - dim succeeded analytically.
        _safe_write_dim_state(
            run_dir, dimension, DimState.DONE,
            exit_reason=ev.exit_reason,
        )
        try:
            result[dimension] = ev
            if on_dimension_done:
                on_dimension_done(dimension, ev)
        except BrokenPipeError:
            # Stdout pipe to parent died mid-callback. Silence stdout/stderr,
            # then retry the callback once so the scoring side effects
            # (evaluation/<dim>.json) actually land on disk. See the matching
            # block in run_incremental_loop for rationale.
            _silence_broken_stdout()
            if on_dimension_done:
                try:
                    on_dimension_done(dimension, ev)
                    log_warning(
                        f"[loop] {dimension} - callback broken pipe, "
                        f"retried after silencing stdout, result persisted",
                    )
                except Exception as exc:  # noqa: BLE001
                    log_warning(
                        f"[loop] {dimension} - callback retry after broken pipe raised "
                        f"{type(exc).__name__}: {exc} - result NOT persisted, continuing loop",
                    )
            else:
                log_warning(f"[loop] {dimension} - callback broken pipe, no retry needed, continuing loop")
        except Exception as exc:  # noqa: BLE001
            log_warning(
                f"[loop] {dimension} - callback raised "
                f"{type(exc).__name__}: {exc} - result kept, continuing loop",
            )
        log_info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (ev=set)")
    log_info(
        f"[loop] per-dimension finished: processed {len(result)} of {len(dimensions)} dim(s) "
        f"({', '.join(result) if result else 'none'}, {skipped_count} skipped)",
    )
    check_zero_findings(
        result, config.source_file_count, skipped_count,
        incremental_filter_active=config.options.incremental_file_filter is not None
            or config.options.skip_scoring,
    )
    check_model_reachable(_run_dir_for(config), result)
    return result
