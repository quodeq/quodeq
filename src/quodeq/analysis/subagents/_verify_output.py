"""Finding verification output — writing findings and grouping by file."""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path


def write_carry_forward_findings(
    findings: list[dict], evidence_dir: Path, dim_id: str,
    write_fn: Callable[[Path, str], None] | None = None,
) -> int:
    """Append carry-forward findings to the evidence JSONL.

    Writes from an in-memory list of finding dicts (as returned by
    partition_findings_by_fingerprint). Unlike carry_forward_findings in
    incremental.py which filters file-to-file, this writes pre-partitioned
    results directly.

    *write_fn* is an injectable writer ``(path, text) -> None``.  Defaults
    to creating parent dirs and appending to file.

    Returns the number of findings written.
    """
    if not findings:
        return 0
    output = evidence_dir / f"{dim_id}_evidence.jsonl"
    if write_fn:
        text = "".join(json.dumps(finding) + "\n" for finding in findings)
        write_fn(output, text)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "a") as f:
            for finding in findings:
                f.write(json.dumps(finding))
                f.write("\n")
    return len(findings)


def _group_by_file(findings: list[dict]) -> dict[str, list[dict]]:
    """Group findings by their source file path."""
    groups: dict[str, list[dict]] = {}
    for finding in findings:
        file_path = finding.get("file", "")
        if file_path:
            groups.setdefault(file_path, []).append(finding)
    return groups


def _write_verify_manifest(
    grouped: dict[str, list[dict]],
    output_path: Path,
) -> None:
    """Write the verification manifest — a JSON file mapping files to findings.

    Each verification subagent reads this to know which findings to re-check.
    """
    output_path.write_text(json.dumps(grouped, indent=2))
