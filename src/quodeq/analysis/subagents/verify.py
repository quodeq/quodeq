"""Finding verification — re-checks previous findings using a fast AI pool.

Two-phase approach:
1. Mechanical pre-filter: drop findings whose files no longer exist (instant)
2. AI verification pool: dispatch remaining findings to fast model subagents
   grouped by file, each agent reads the current code and confirms/drops

Confirmed findings are written to the evidence JSONL via MCP (same as
main analysis), so they appear on the dashboard immediately.

This module is the public entry point; implementation is split across:
- _verify_io: evidence path resolution and JSONL parsing
- _verify_filter: pre-filtering and fingerprint classification
- _verify_output: writing findings and grouping by file
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.analysis.subagents._verify_filter import (  # noqa: F401
    _classify_findings,
    _pre_filter_gone,
    partition_findings_by_fingerprint,
)
from quodeq.analysis.subagents._verify_io import (  # noqa: F401
    _find_previous_evidence,
    _load_previous_findings,
    _parse_finding_line,
    _resolve_previous_evidence,
    resolve_evidence_paths,
)
from quodeq.analysis.subagents._verify_output import (  # noqa: F401
    _group_by_file,
    _write_verify_manifest,
    write_carry_forward_findings,
)
from quodeq.analysis.subagents._verify_pool import build_verify_prompt  # noqa: F401 — re-export
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
    so multiple callers (priority scoring, verification) don't repeat file
    I/O within the same run.  Pass ``None`` to disable caching.

    Returns list of findings to verify (may be empty).
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
