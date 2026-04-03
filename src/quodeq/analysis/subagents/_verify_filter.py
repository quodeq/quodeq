"""Finding verification filters — pre-filtering and fingerprint classification."""
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


def _classify_findings(
    findings: list[dict], prev_hashes: dict, src: Path,
) -> tuple[list[dict], list[dict]]:
    """Classify findings into carry-forward vs needs-verification by file hash."""
    from quodeq.analysis.fingerprint import _hash_file
    file_unchanged: dict[str, bool] = {}
    carry_forward: list[dict] = []
    needs_verification: list[dict] = []
    for finding in findings:
        rel_path = finding.get("file", "")
        if not rel_path:
            needs_verification.append(finding)
            continue
        if rel_path not in file_unchanged:
            prev_hash = prev_hashes.get(rel_path)
            if prev_hash is None:
                file_unchanged[rel_path] = False
            else:
                file_unchanged[rel_path] = _hash_file(src / rel_path) == prev_hash
        if file_unchanged[rel_path]:
            carry_forward.append(finding)
        else:
            needs_verification.append(finding)
    return carry_forward, needs_verification


def partition_findings_by_fingerprint(
    findings: list[dict],
    prev_fingerprint: dict | None,
    src: Path,
    standards_dir: Path | None = None,
    dimension: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Split findings into (carry_forward, needs_verification) based on file hashes.

    Uses the previous fingerprint's per-file SHA-256 hashes to determine which
    files have changed. Findings for unchanged files are carried forward (no AI
    needed); findings for changed/deleted/new files need AI verification.

    If standards changed since the previous run, all findings need verification
    regardless of file hashes (findings were evaluated under different criteria).
    """
    from quodeq.analysis.fingerprint import _hash_standards

    if not prev_fingerprint or not findings:
        return [], list(findings)

    # Standards guard: if standards changed, all findings need verification
    if standards_dir and dimension:
        current_std = _hash_standards(standards_dir, dimension)
        prev_std = prev_fingerprint.get("standards_checksum")
        if prev_std is not None and current_std != prev_std:
            return [], list(findings)

    return _classify_findings(findings, prev_fingerprint.get("file_hashes", {}), src)
