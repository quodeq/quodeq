"""Verification step helpers — extracted from runner.py for file-length limits."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from copy import copy

from quodeq.analysis._types import RunConfig
from quodeq.analysis.fingerprint import find_previous_fingerprint
from quodeq.analysis.subagents._verify_pool import run_verification_pool
from quodeq.analysis.subagents.verify import (
    load_previous_findings_for_dimension,
    partition_findings_by_fingerprint,
    write_carry_forward_findings,
    _group_by_file,
    _write_verify_manifest,
)
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.shared.logging import log_info, log_success


def _run_verification_pool(
    config: RunConfig, dim_id: str, evidence_dir: Path,
    files_to_verify: list[str], manifest_path: Path,
) -> list[Any]:
    """Launch a fast verification pool to re-check previous findings."""
    return run_verification_pool(config, dim_id, evidence_dir, files_to_verify, manifest_path)


def _load_and_filter_previous(
    config: RunConfig, dim_id: str, evidence_dir: Path,
) -> list[dict]:
    """Load previous findings and apply incremental file filter if active."""
    prev_findings = load_previous_findings_for_dimension(config, dim_id, evidence_dir)
    if not prev_findings:
        return []
    if config.options.incremental_file_filter is not None:
        filter_set = config.options.incremental_file_filter
        prev_findings = [f for f in prev_findings if f.get("file") in filter_set]
    # Filter out dismissed and permanently-deleted findings
    project_dir = evidence_dir.parent
    dkeys = dismissed_keys(project_dir)
    delkeys = deleted_keys(project_dir)
    if dkeys:
        prev_findings = [
            f for f in prev_findings
            if (f.get("p", ""), f.get("file", ""), f.get("line", 0)) not in dkeys
        ]
    if delkeys:
        prev_findings = [
            f for f in prev_findings
            if (dim_id, f.get("p", ""), f.get("file", "")) not in delkeys
        ]
    return prev_findings


def _dispatch_verification_pool(
    config: RunConfig, dim_id: str, evidence_dir: Path, needs_verify: list[dict],
) -> list:
    """Write manifest and launch the AI verification pool for changed-file findings."""
    grouped = _group_by_file(needs_verify)
    manifest_path = evidence_dir / f"{dim_id}_verify_manifest.json"
    _write_verify_manifest(grouped, manifest_path)
    files_to_verify = list(grouped.keys())
    log_info(f"  [{dim_id}] [VERIFICATION] Launching pool for {len(needs_verify)} findings across {len(files_to_verify)} files")
    verify_results = _run_verification_pool(config, dim_id, evidence_dir, files_to_verify, manifest_path)
    log_success(f"  [{dim_id}] [VERIFICATION] Pool complete")
    return verify_results


_MINI_VERIFY_MIN_TIMEOUT_S = 60
_MINI_VERIFY_MAX_AGENTS = int(os.environ.get("QUODEQ_MINI_VERIFY_MAX_AGENTS", "2"))
_MINI_VERIFY_TIMEOUT_PER_10 = int(os.environ.get("QUODEQ_MINI_VERIFY_TIMEOUT_PER_10", "60"))
_MINI_VERIFY_MAX_TIMEOUT = int(os.environ.get("QUODEQ_MINI_VERIFY_MAX_TIMEOUT", "300"))


def _dispatch_mini_verify(
    config: RunConfig, dim_id: str, evidence_dir: Path, findings: list,
) -> list:
    """Post-analysis mini-verify for changed files not in the analysis queue."""
    if not findings:
        return []

    grouped = _group_by_file(findings)
    manifest_path = evidence_dir / f"{dim_id}_mini_verify_manifest.json"
    _write_verify_manifest(grouped, manifest_path)
    files_to_verify = list(grouped.keys())

    n_files = len(files_to_verify)
    timeout = min(_MINI_VERIFY_MAX_TIMEOUT, max(_MINI_VERIFY_MIN_TIMEOUT_S, (n_files // 10 + 1) * _MINI_VERIFY_TIMEOUT_PER_10))

    log_info(f"  [{dim_id}] [MINI-VERIFY] {len(findings)} findings across {n_files} changed files (not in analysis queue)")

    mini_config = copy(config)
    mini_options = copy(config.options)
    mini_options.time_limit = timeout
    mini_options.max_subagents = min(_MINI_VERIFY_MAX_AGENTS, config.options.max_subagents)
    mini_config.options = mini_options

    results = _run_verification_pool(mini_config, dim_id, evidence_dir, files_to_verify, manifest_path)
    log_success(f"  [{dim_id}] [MINI-VERIFY] Complete")
    return results


def _run_verification_step(
    config: RunConfig, dim_id: str, evidence_dir: Path, files: list[str],
    prev_fingerprint: dict | None = None,
) -> list:
    """Load previous findings and run AI verification pool if needed.

    Uses fingerprint hashes to skip verification for unchanged files —
    their findings are carried forward directly to the evidence JSONL.
    Only changed-file findings are sent to the AI verification pool.
    """
    prev_findings = _load_and_filter_previous(config, dim_id, evidence_dir)
    if not prev_findings:
        return []

    if not config.options.incremental:
        # Clean scan: every previous finding goes back through verification.
        log_info(f"  [{dim_id}] Clean scan — re-verifying all previous findings")
        carry_forward: list[dict] = []
        needs_verify: list[dict] = list(prev_findings)
    else:
        if prev_fingerprint is None:
            prev_fingerprint, _ = find_previous_fingerprint(evidence_dir, dim_id)
            if prev_fingerprint is None:
                log_info(f"  [{dim_id}] No previous fingerprint — all findings need verification")

        carry_forward, needs_verify = partition_findings_by_fingerprint(
            prev_findings, prev_fingerprint, config.src,
            standards_dir=config.standards_dir, dimension=dim_id,
        )
    if carry_forward:
        written = write_carry_forward_findings(carry_forward, evidence_dir, dim_id)
        log_info(f"  [{dim_id}] {written} findings carried forward (unchanged files)")
    if not needs_verify:
        log_info(f"  [{dim_id}] All previous findings carried forward — skipping verification pool")
        return []

    return _dispatch_verification_pool(config, dim_id, evidence_dir, needs_verify)
