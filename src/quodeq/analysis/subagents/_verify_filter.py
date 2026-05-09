"""Pre-filter for prior findings — drops findings whose files no longer exist.

Post-V2 (B6.2b): only ``_pre_filter_gone`` survives. The fingerprint-
based partition logic (``partition_findings_by_fingerprint``,
``_classify_findings``) was specific to the V1 verify-pool, which V2
replaces with content-addressed cache invalidation.

This module is still referenced because ``priority_scoring`` reads
prior findings to weight the file queue, and a finding pointing at a
deleted file is meaningless for priority.
"""
from __future__ import annotations

from pathlib import Path


def _pre_filter_gone(findings: list[dict], src: Path) -> tuple[list[dict], int]:
    """Fast pre-filter: drop findings whose files no longer exist.

    Returns (surviving_findings, gone_count).
    """
    # Batch existence checks: resolve unique paths once instead of per-finding.
    unique_paths: dict[str, bool] = {}
    for finding in findings:
        rel_path = finding.get("file", "")
        if rel_path and rel_path not in unique_paths:
            unique_paths[rel_path] = (src / rel_path).exists()

    surviving: list[dict] = []
    gone = 0
    for finding in findings:
        rel_path = finding.get("file", "")
        if not rel_path or not unique_paths.get(rel_path, False):
            gone += 1
        else:
            surviving.append(finding)
    return surviving, gone
