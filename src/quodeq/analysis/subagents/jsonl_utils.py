"""JSONL merge and deduplication utilities for subagent pool output."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from quodeq.core.evidence._req_mapping import PrincipleResolver
from quodeq.shared.logging import log_info
from quodeq.shared.utils import open_text

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FindingTally:
    """Unique violation/compliance counts plus the duplicates folded out."""
    violations: int = 0
    compliance: int = 0
    duplicates: int = 0
    quarantined: int = 0

    @property
    def total(self) -> int:
        return self.violations + self.compliance


def tally_unique_findings(
    jsonl_path: Path, resolver: PrincipleResolver | None = None,
) -> FindingTally:
    """Count unique findings (deduplicated by ``(p, file, line, t)``) and duplicates.

    Single source of truth for the heartbeat and the dashboard progress reader,
    so the terminal and UI never disagree mid-batch — before the on-disk
    :func:`deduplicate_jsonl` pass runs at end of pool, the file holds raw
    appends from many parallel agents and contains overlapping findings.

    When *resolver* is supplied, findings whose principle is not in the
    dimension's standard are counted under ``quarantined`` instead of
    ``violations``/``compliance`` — matching what the report path drops in
    :func:`~quodeq.core.evidence._req_mapping._group_judgments`, so the live
    counter and the persisted evaluation agree. Without a resolver the tally
    stays permissive and counts every finding, since there is no standard to
    validate against.

    Deduplication happens before the quarantine check, so a repeated unmappable
    finding is one quarantined entry, not one per copy.

    Tolerant: missing files, malformed lines, and OSError yield empty/partial
    tallies silently.
    """
    if not jsonl_path.is_file():
        return FindingTally()
    seen: set[tuple] = set()
    violations = compliance = duplicates = quarantined = 0
    try:
        with open_text(jsonl_path) as f:
            for raw in f:
                stripped = raw.strip()
                if not stripped:
                    continue
                try:
                    obj = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                t = obj.get("t")
                key = (obj.get("p"), obj.get("file"), obj.get("line"), t)
                if key in seen:
                    duplicates += 1
                    continue
                seen.add(key)
                if t not in ("violation", "compliance"):
                    # Non-finding rows (e.g. the file_done markers the pool
                    # appends) still occupy a dedup key but classify as neither.
                    continue
                # Mirror parse_jsonl_line: `p` wins, `req` is the fallback.
                if resolver is not None and resolver.resolve(obj.get("p") or obj.get("req")) is None:
                    quarantined += 1
                    continue
                if t == "violation":
                    violations += 1
                else:
                    compliance += 1
    except OSError:
        pass
    return FindingTally(
        violations=violations, compliance=compliance,
        duplicates=duplicates, quarantined=quarantined,
    )


def dedup_jsonl_lines(lines: Iterable[str]) -> list[str]:
    """Deduplicate JSONL lines by ``(p, file, line, t)`` key.

    Returns a list of stripped, unique JSON lines.
    """
    return list(_iter_dedup_jsonl_lines(lines))


def _iter_dedup_jsonl_lines(lines: Iterable[str]) -> Iterable[str]:
    """Yield unique JSONL lines, deduplicating by ``(p, file, line, t)`` key.

    Uses a set for seen keys and yields each unique line immediately,
    avoiding accumulation of all lines in memory.
    """
    seen: set[tuple] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            _logger.debug("Skipping malformed JSONL line: %.100s", stripped)
            continue
        key = (obj.get("p"), obj.get("file"), obj.get("line"), obj.get("t"))
        if key in seen:
            continue
        seen.add(key)
        yield stripped


def deduplicate_jsonl(jsonl_path: Path) -> int:
    """Deduplicate a JSONL file in-place by (p, file, line, t).

    Returns the number of unique findings kept.
    """
    if not jsonl_path.exists():
        return 0
    # Read first, then overwrite — must fully consume before writing to same file
    with open_text(jsonl_path) as f:
        unique_lines = dedup_jsonl_lines(f)
    with open_text(jsonl_path, "w") as f:
        for line in unique_lines:
            f.write(line + "\n")
    log_info(f"Deduplicated {jsonl_path.name}: {len(unique_lines)} unique findings")
    return len(unique_lines)


def merge_jsonl(result_jsonl_files: Iterable[Path], output: Path) -> Path:
    """Merge JSONL files, deduplicating by (p, file, line, t).

    Writes deduplicated lines directly to the output file as they are found
    unique, avoiding accumulation of all lines in memory.

    Returns the output path.
    """
    def _iter_all_lines() -> Iterable[str]:
        for jsonl_file in result_jsonl_files:
            if not jsonl_file.exists():
                continue
            with open_text(jsonl_file) as f:
                yield from f

    count = 0
    with open_text(output, "w") as out:
        for line in _iter_dedup_jsonl_lines(_iter_all_lines()):
            out.write(line + "\n")
            count += 1
    log_info(f"Merged {count} unique findings into {output.name}")
    return output
