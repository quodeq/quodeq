"""Read a run's finding identity keys (for per-run cache-version scoping).

A run's score depends only on the suppressions whose keys are present in that
run, so the score cache versions each run by (dismissed ∩ these) + (deleted ∩
these). Keys come from ALL findings regardless of verdict, so a dismiss (which
only flips a verdict) never changes a run's key set. Best-effort: an
unreadable/absent db yields empty sets.

The SQL itself lives in the data layer (``findings_queries``); this module
is the service-facing facade.
"""
from __future__ import annotations

from quodeq.data.sqlite.findings_queries import read_run_key_sets

__all__ = ["read_run_key_sets"]
