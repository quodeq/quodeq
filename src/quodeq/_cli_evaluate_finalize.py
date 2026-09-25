"""run_evaluate's diff-from resolution and post-run finalization (SARIF export).

Split out of ``cli_evaluation.py`` to keep that file under the size
ratchet's 300-line cap. ``apply_diff_from`` and ``finalize_run_evaluate``
are called only from ``cli_evaluation.run_evaluate``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable, Iterable

from quodeq._cli_resolution import ResolvedInputs
from quodeq.analysis.cache.consolidation import mark_run_consolidated
from quodeq.analysis.diff_resolver import DiffResolveError
from quodeq.shared.fault_isolation import run_isolated
from quodeq.shared.log_sink import SHARED_LOG
from quodeq.shared.logging import log_error, log_info, log_warning


def apply_diff_from(
    args: argparse.Namespace, inputs: ResolvedInputs, resolve_diff_files: Callable[[Path, str], Iterable[str]],
) -> int | None:
    """Resolve --diff-from into args._diff_files. Returns an exit code on
    failure, or None on success (including the no --diff-from case).

    Resolved here (not inside build_run_config) so a DiffResolveError fails
    fast before any run directory is created — once a run dir exists, its
    state is always written by RunLifecycleContext. *resolve_diff_files* is
    passed in by ``run_evaluate`` so the ``quodeq.cli_evaluation`` patch
    target keeps working without this module importing its importer.
    """
    diff_from = getattr(args, "diff_from", None)
    if not diff_from:
        args._diff_files = None
        return None
    try:
        args._diff_files = set(resolve_diff_files(inputs.src, diff_from))
    except DiffResolveError as exc:
        log_error(f"Error: could not resolve --diff-from {diff_from!r}: {exc}")
        return 1
    log_info(f"PR diff mode: {len(args._diff_files)} changed file(s) vs {diff_from}")
    return None


def write_sarif_if_requested(args: argparse.Namespace, evaluation_dir: Path) -> None:
    """Write a SARIF file if --sarif was passed. Fail-soft: never raises.

    Called from run_evaluate AFTER the run lifecycle has fully closed, so a
    failure here can never flip a successful run to failed. The scored reports
    are already on disk in evaluation_dir.
    """
    sarif_path = getattr(args, "sarif", None)
    if not sarif_path:
        return
    try:
        from quodeq import __version__
        from quodeq.ci.reporter import load_evaluation_reports
        from quodeq.ci.sarif import build_sarif

        reports = load_evaluation_reports(evaluation_dir)
        doc = build_sarif(
            reports,
            tool_version=__version__ or "0.0.0+dev",
            min_severity=getattr(args, "min_severity", None),
            include_snippets=getattr(args, "with_snippets", False),
        )
        out = Path(sarif_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        count = sum(len(r["results"]) for r in doc["runs"])
        log_info(f"Wrote {count} finding(s) to SARIF: {out}")
    except Exception as exc:  # noqa: BLE001 — fail-soft: SARIF must never sink a scan
        log_warning(f"SARIF export failed (evaluation results are safe): {exc}")


def _consolidate_run_cache(evaluation_dir: Path) -> None:
    """Post-run cache consolidation, isolated from the run's own result.

    ``mark_run_consolidated`` is already fail-soft internally (its own
    whole-body catch degrades on (OSError, ValueError) rather than raising),
    but this call sits after the run lifecycle has closed and
    finalize_run_evaluate's return value becomes the process exit code -- so
    an exception type that guard doesn't recognize must still never turn a
    finished run's zero exit code into a nonzero one. ``run_isolated`` is
    that backstop. Tests patch ``quodeq._cli_evaluate_finalize.mark_run_consolidated``
    -- mock.patch resolves where a name is used, not where it's defined.
    """
    run_isolated(
        lambda: mark_run_consolidated(evaluation_dir.parent),
        label="post-run cache consolidation", log=SHARED_LOG,
    )


def finalize_run_evaluate(args: argparse.Namespace, evaluation_dir: Path, result: int) -> int:
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
        _consolidate_run_cache(evaluation_dir)
    # Only export SARIF on success and only when scored reports exist.
    if result == 0 and getattr(args, "sarif", None) and not no_scored_reports:
        write_sarif_if_requested(args, evaluation_dir)
    return result
