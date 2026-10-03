"""Read a run's finding identity keys (for per-run cache-version scoping).

A run's score depends only on the suppressions whose keys are present in that
run, so the score cache versions each run by (dismissed ∩ these) + (deleted ∩
these). Keys come from ALL findings regardless of verdict, so a dismiss (which
only flips a verdict) never changes a run's key set.

The keys come from the run's ``evaluation.db`` (``findings_queries``) when it
has one, and from its evaluation reports otherwise (``read_report_key_sets``),
so a legacy JSON-only run is versioned and touch-checked like any other
instead of passing for a run no suppression can reach. Best-effort: an
unreadable db or a run without reports yields empty sets.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.services.wiring import has_evaluation_db, read_report_key_sets, read_run_key_sets_from_db


def read_run_key_sets(run_dir: Path) -> tuple[set[tuple], set[tuple]]:
    """``(dismiss_keys, class_keys)`` present in *run_dir*'s findings."""
    if has_evaluation_db(run_dir):
        return read_run_key_sets_from_db(run_dir)
    return read_report_key_sets(run_dir)


__all__ = ["read_run_key_sets"]
