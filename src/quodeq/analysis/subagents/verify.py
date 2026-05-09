"""Prior-findings reader — used by priority scoring and the V2 cache layer.

Post-V2 (B6.2b): the verify-pool dispatch is gone. What remains in
this module is the *reader*: ``load_previous_findings_for_dimension``
loads, pre-filters, and returns prior findings for callers that want
to use them as input (e.g., priority scoring weights newly-changed
files higher when prior findings exist).

The verify-pool's role — re-validating prior findings when standards
change — is now structurally redundant: V2's content-addressed cache
key includes ``standards_hash`` and ``prompts_hash``, so any change
invalidates entries and triggers full fresh dispatch.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.analysis.subagents._verify_filter import _pre_filter_gone
from quodeq.analysis.subagents._verify_io import (  # noqa: F401 — re-exports
    _resolve_previous_evidence,
    resolve_evidence_paths,
)
from quodeq.analysis.subagents._verify_io import _load_previous_findings
from quodeq.shared.logging import log_info


def load_previous_findings_for_dimension(
    config: Any,
    dim_id: str,
    evidence_dir: Path,
    *,
    quiet: bool = False,
    cache: dict[tuple[str, str], tuple[list[dict], int, int]] | None = None,
) -> list[dict]:
    """Load and pre-filter previous findings for a dimension.

    When *cache* is provided, results are stored per (evidence_dir, dim_id)
    so multiple callers don't repeat file I/O within the same run.  Pass
    ``None`` to disable caching.

    Returns list of surviving findings (files still exist).
    """
    if not getattr(config, 'options', None) or not config.options.verify_findings:
        return []

    cache_key = (str(evidence_dir), dim_id)
    if cache is not None:
        cached = cache.get(cache_key)
        if cached is not None:
            surviving, total, gone = cached
            if not quiet and total > 0:
                log_info(f"  [{dim_id}] {total} previous findings: {gone} files gone, {len(surviving)} surviving")
            return surviving

    prev_jsonl, _ = _resolve_previous_evidence(evidence_dir, dim_id, cache, cache_key)
    if prev_jsonl is None:
        if not quiet:
            log_info(f"  [{dim_id}] No previous evaluation — skipping verification")
        return []

    prev_findings = _load_previous_findings(prev_jsonl)
    if not prev_findings:
        if cache is not None:
            cache[cache_key] = ([], 0, 0)
        return []

    surviving, gone = _pre_filter_gone(prev_findings, config.src)
    if not quiet:
        log_info(f"  [{dim_id}] {len(prev_findings)} previous findings: {gone} files gone, {len(surviving)} surviving")
    if cache is not None:
        cache[cache_key] = (surviving, len(prev_findings), gone)
    return surviving
