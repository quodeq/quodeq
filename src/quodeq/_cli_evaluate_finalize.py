"""run_evaluate's diff-from resolution and post-run finalization.

Split out of ``_cli_evaluation.py`` to keep that file under the size
ratchet's 300-line cap. Both pieces are called only from
``_cli_evaluation.run_evaluate`` and were moved verbatim.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from quodeq._cli_resolution import ResolvedInputs
from quodeq._cli_lifecycle import _write_sarif_if_requested
from quodeq.analysis._diff_resolver import DiffResolveError
from quodeq.shared.logging import log_error, log_info


def _apply_diff_from(args: argparse.Namespace, inputs: ResolvedInputs) -> int | None:
    """Resolve --diff-from into args._diff_files. Returns an exit code on
    failure, or None on success (including the no --diff-from case).

    Resolved here (not inside _build_run_config) so a DiffResolveError fails
    fast before any run directory is created — once a run dir exists, its
    state is always written by RunLifecycleContext.
    """
    diff_from = getattr(args, "diff_from", None)
    if not diff_from:
        args._diff_files = None
        return None
    # Deferred facade lookup: tests patch quodeq._cli_evaluation.resolve_diff_files
    # (the historical, still-public call site), not this module's own import.
    from quodeq import _cli_evaluation as _facade
    try:
        args._diff_files = set(_facade.resolve_diff_files(inputs.src, diff_from))
    except DiffResolveError as exc:
        log_error(f"Error: could not resolve --diff-from {diff_from!r}: {exc}")
        return 1
    log_info(f"PR diff mode: {len(args._diff_files)} changed file(s) vs {diff_from}")
    return None


def _finalize_run_evaluate(args: argparse.Namespace, evaluation_dir: Path, result: int) -> int:
    """Fail-soft consolidation + SARIF export, run OUTSIDE the run lifecycle
    (already closed) so a failure here can never flip the run state."""
    # --diff-from / --evidence-only produce no scored reports: nothing to export.
    no_scored_reports = bool(
        getattr(args, "diff_from", None) or getattr(args, "evidence_only", False)
    )
    # Marks this run's cache entries consolidated so the NEXT run replays their
    # findings as carried forward; gated internally on status.json reading "done"
    # (a cancelled/failed/killed run leaves entries unconsolidated, so their
    # findings still read as new in the live feed).
    if not no_scored_reports:
        from quodeq.analysis.cache.consolidation import mark_run_consolidated
        mark_run_consolidated(evaluation_dir.parent)
    # Only export SARIF on success and only when scored reports exist.
    if result == 0 and getattr(args, "sarif", None) and not no_scored_reports:
        _write_sarif_if_requested(args, evaluation_dir)
    return result
