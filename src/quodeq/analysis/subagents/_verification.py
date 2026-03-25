"""Verification step helpers — extracted from runner.py for file-length limits."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from quodeq.shared.logging import log_info, log_success

if TYPE_CHECKING:
    from quodeq.analysis.runner import RunConfig


def _run_verification_pool(
    config: RunConfig, dim_id: str, evidence_dir: Path,
    files_to_verify: list[str], manifest_path: Path,
) -> list[Any]:
    """Launch a fast verification pool to re-check previous findings."""
    from quodeq.analysis.subagents._verify_pool import run_verification_pool
    return run_verification_pool(config, dim_id, evidence_dir, files_to_verify, manifest_path)


def _load_and_filter_previous(
    config: RunConfig, dim_id: str, evidence_dir: Path,
) -> list[dict]:
    """Load previous findings and apply incremental file filter if active."""
    from quodeq.analysis.subagents.verify import load_previous_findings_for_dimension

    prev_findings = load_previous_findings_for_dimension(config, dim_id, evidence_dir)
    if not prev_findings:
        return []
    if config.options.incremental_file_filter is not None:
        filter_set = config.options.incremental_file_filter
        prev_findings = [f for f in prev_findings if f.get("file") in filter_set]
    return prev_findings


def _dispatch_verification_pool(
    config: RunConfig, dim_id: str, evidence_dir: Path, needs_verify: list[dict],
) -> list:
    """Write manifest and launch the AI verification pool for changed-file findings."""
    from quodeq.analysis.subagents.verify import _group_by_file, _write_verify_manifest

    grouped = _group_by_file(needs_verify)
    manifest_path = evidence_dir / f"{dim_id}_verify_manifest.json"
    _write_verify_manifest(grouped, manifest_path)
    files_to_verify = list(grouped.keys())
    log_info(f"  [{dim_id}] Launching fast verification pool for {len(needs_verify)} findings across {len(files_to_verify)} files")
    verify_results = _run_verification_pool(config, dim_id, evidence_dir, files_to_verify, manifest_path)
    log_success(f"  [{dim_id}] Verification pool complete")
    return verify_results


def _run_verification_step(
    config: RunConfig, dim_id: str, evidence_dir: Path, files: list[str],
    prev_fingerprint: dict | None = None,
) -> list:
    """Load previous findings and run AI verification pool if needed.

    Uses fingerprint hashes to skip verification for unchanged files —
    their findings are carried forward directly to the evidence JSONL.
    Only changed-file findings are sent to the AI verification pool.
    """
    from quodeq.analysis.subagents.verify import (
        partition_findings_by_fingerprint, write_carry_forward_findings,
    )

    prev_findings = _load_and_filter_previous(config, dim_id, evidence_dir)
    if not prev_findings:
        return []

    if prev_fingerprint is None:
        from quodeq.analysis.fingerprint import find_previous_fingerprint
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
