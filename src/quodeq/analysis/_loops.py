"""Dimension loop orchestrators — run dimensions sequentially or incrementally."""
from __future__ import annotations

import json
import os
import sys
from copy import copy
from dataclasses import replace
from collections.abc import Callable

from quodeq.analysis._incremental_orchestrator import run_dimension_incremental
from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis.errors import EvaluationError
from quodeq.core.evidence.model import Evidence
from quodeq.engine._runner_markers import emit_marker
# NOTE: logging in inner layer — tracked for middleware extraction
from quodeq.shared.logging import log_info, log_warning


def _silence_broken_stdout() -> None:
    """Redirect stdout/stderr to /dev/null after a BrokenPipeError.

    Once the parent has closed its end of the pipe every subsequent write to
    stdout/stderr raises BrokenPipeError. The actual analysis work (evidence
    files, MCP calls, etc.) doesn't depend on those streams — only logging
    does. Swapping the streams to /dev/null lets remaining dimensions run.
    """
    try:
        devnull = open(os.devnull, "w")  # noqa: SIM115 — long-lived
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
    changed-file set that may contain none of the dimension's language) —
    skip the check. Otherwise a genuinely empty result is almost always a
    symptom of a broken AI CLI tool loop, not a clean codebase.
    """
    if not result or source_file_count <= 0 or incremental_filter_active:
        return
    total_findings = sum(
        sum(len(pe.violations) + len(pe.compliance) for pe in ev.principles.values())
        for ev in result.values()
    )
    if total_findings == 0:
        skip_msg = f" ({skipped_count} skipped)" if skipped_count else ""
        raise EvaluationError(
            f"Evaluation produced 0 findings across {len(result)} dimensions{skip_msg}. "
            f"This usually means the AI CLI could not read files or report findings "
            f"\u2014 check tool permissions and MCP configuration."
        )


def run_incremental_loop(
    config: RunConfig, dimensions: list[str], ctx: _AnalysisContext,
    *, process_fn: Callable[..., Evidence | None],
    log_result_fn: Callable[..., None],
    on_dimension_done: Callable[[str, Evidence], None] | None = None,
) -> dict[str, Evidence]:
    """Run incremental per-dimension analysis.

    Args:
        config: Run configuration for this evaluation.
        dimensions: Dimension identifiers to analyze.
        ctx: Shared analysis context (total count, etc.).
        process_fn: Callback to process a single dimension (signature:
            ``(config, dimension, idx, ctx) -> Evidence | None``).
        log_result_fn: Callback to log a completed dimension result.
    """
    result: dict[str, Evidence] = {}
    log_info(f"[loop] incremental: {len(dimensions)} dim(s) to process: {', '.join(dimensions)}")
    for idx, dimension in enumerate(dimensions, 1):
        log_info(f"[loop] entering iteration {idx}/{ctx.total} for {dimension}")
        emit_marker("analyzing", dimension=dimension)
        log_info(f"\u2192 [{idx}/{ctx.total}] Analyzing {dimension} (incremental)")
        ev: Evidence | None = None
        try:
            ev = run_dimension_incremental(config, dimension, idx, ctx)
        except BrokenPipeError:
            _silence_broken_stdout()
            ev = None
        except (OSError, KeyError, ValueError, RuntimeError) as exc:
            log_warning(f"[{idx}/{ctx.total}] {dimension} \u2014 incremental failed: {exc}, falling back to full")
            fallback_options = copy(config.options)
            fallback_options.incremental_file_filter = None
            fallback_config = replace(config, options=fallback_options)
            try:
                ev = process_fn(fallback_config, dimension, idx, ctx)
            except BrokenPipeError:
                _silence_broken_stdout()
                ev = None
        except Exception as exc:  # noqa: BLE001
            # Loop-level diagnostic: an unanticipated exception class would
            # otherwise propagate up silently and the lifecycle would treat
            # it as failed without saying which dim. Log + swallow + continue
            # so subsequent dims still run; the surfaced log line gives us
            # the trail we need next time this happens.
            log_warning(
                f"[loop] {dimension} \u2014 unexpected exception "
                f"{type(exc).__name__}: {exc} \u2014 skipping dim, continuing loop",
            )
            ev = None
        # log_result_fn / on_dimension_done are caller-provided (e.g., the
        # dashboard's scoring callback). Wrap them too \u2014 an exception in a
        # callback shouldn't drop the next iteration on the floor.
        if ev:
            try:
                log_result_fn(ev, dimension, idx, ctx.total)
                result[dimension] = ev
                if on_dimension_done:
                    on_dimension_done(dimension, ev)
            except BrokenPipeError:
                # Stdout pipe to parent died (the most likely cause of the
                # silent-skip bug observed in production: log_success or the
                # dashboard's scoring callback writes to a closed parent
                # pipe). Keep result, log the trail, continue to next dim
                # instead of letting it bubble out and lifecycle quietly
                # converting it to state=done.
                _silence_broken_stdout()
                result.setdefault(dimension, ev)
                log_warning(f"[loop] {dimension} \u2014 callback broken pipe, result kept, continuing loop")
            except Exception as exc:  # noqa: BLE001
                log_warning(
                    f"[loop] {dimension} \u2014 callback raised "
                    f"{type(exc).__name__}: {exc} \u2014 result kept, continuing loop",
                )
                result.setdefault(dimension, ev)
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
    return result


def run_per_dimension_loop(
    config: RunConfig, dimensions: list[str], ctx: _AnalysisContext,
    *, process_fn: Callable[..., Evidence | None],
    on_dimension_done: Callable[[str, Evidence], None] | None = None,
) -> dict[str, Evidence]:
    """Per-dimension loop (fallback or single-dimension).

    Args:
        config: Run configuration for this evaluation.
        dimensions: Dimension identifiers to analyze.
        ctx: Shared analysis context (total count, etc.).
        process_fn: Callback to process a single dimension (signature:
            ``(config, dimension, idx, ctx) -> Evidence | None``).
    """
    result: dict[str, Evidence] = {}
    skipped_count = 0
    log_info(f"[loop] per-dimension: {len(dimensions)} dim(s) to process: {', '.join(dimensions)}")
    for idx, dimension in enumerate(dimensions, 1):
        log_info(f"[loop] entering iteration {idx}/{ctx.total} for {dimension}")
        ev: Evidence | None = None
        try:
            ev = process_fn(config, dimension, idx, ctx)
        except BrokenPipeError:
            _silence_broken_stdout()
            skipped_count += 1
            log_info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (skipped: broken pipe)")
            continue
        except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
            log_warning(f"[{idx}/{ctx.total}] {dimension} \u2014 failed: {exc}")
            skipped_count += 1
            log_info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (skipped: {type(exc).__name__})")
            continue
        except Exception as exc:  # noqa: BLE001
            # Don't let an exotic exception class drop the rest of the loop
            # silently. Log + count as skipped + continue so we get the trail.
            log_warning(
                f"[loop] {dimension} — unexpected exception "
                f"{type(exc).__name__}: {exc} — skipping dim, continuing loop",
            )
            skipped_count += 1
            log_info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (skipped: unexpected)")
            continue
        if ev is None:
            skipped_count += 1
            log_info(f"[loop] completed iteration {idx}/{ctx.total} for {dimension} (skipped: ev=None)")
            continue
        try:
            result[dimension] = ev
            if on_dimension_done:
                on_dimension_done(dimension, ev)
        except BrokenPipeError:
            # Stdout pipe to parent died (this is the most likely cause of
            # the silent-skip bug observed in production). Keep result, log
            # the trail, continue to next dim instead of bubbling out.
            _silence_broken_stdout()
            log_warning(f"[loop] {dimension} — callback broken pipe, result kept, continuing loop")
        except Exception as exc:  # noqa: BLE001
            log_warning(
                f"[loop] {dimension} — callback raised "
                f"{type(exc).__name__}: {exc} — result kept, continuing loop",
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
    return result
