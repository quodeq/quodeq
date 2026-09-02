"""Live evidence tally: unique finding counts from a dim's raw evidence jsonl.

Single source of truth for the subagent-pool heartbeat and the dashboard's
live scan-progress reader, so the terminal and UI never disagree mid-batch --
before the on-disk deduplication pass runs at end of pool, the file holds raw
appends from many parallel agents and contains overlapping findings.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from quodeq.core.evidence._req_mapping import PrincipleResolver
from quodeq.shared.utils import open_text


@dataclass(frozen=True)
class FindingTally:
    """Unique violation/compliance counts plus the duplicates folded out.

    ``violations`` is the *net* count the user will see in the report. The two
    exclusions netted out of it are each kept, so a run that dropped most of its
    findings is distinguishable from a clean one:

    - ``suppressed``: unique violations a caller-supplied predicate excluded
      (already dismissed or deleted in the dashboard), which the scanner still
      re-finds on every run.
    - ``quarantined``: findings naming a principle the dimension's standard does
      not define, which the report path drops before scoring.
    """
    violations: int = 0
    compliance: int = 0
    duplicates: int = 0
    suppressed: int = 0
    quarantined: int = 0

    @property
    def total(self) -> int:
        return self.violations + self.compliance


def _classify_finding_row(
    raw: str,
    seen: "set[tuple]",
    *,
    suppressed: "Callable[[dict], bool] | None",
    resolver: PrincipleResolver | None,
) -> str:
    """Classify one raw evidence line, updating *seen* in place.

    Returns "skip" (blank/malformed/non-object/non-finding row),
    "duplicate", "quarantined", "suppressed", "violation", or "compliance"
    -- the caller increments the matching counter.

    *resolver* classifies "quarantined" a finding whose principle is not in
    the dimension's standard, matching the report path's
    :func:`~quodeq.core.evidence._req_mapping._group_judgments`. *suppressed*
    (see ``quodeq.services.suppression``, injected to keep this module free
    of a services dependency) classifies "suppressed" a violation the user
    already dismissed or deleted. Quarantine is checked first: a finding
    with no principle in the standard has no valid delete key, so asking
    whether it was suppressed is not meaningful. Without either argument,
    every finding classifies as "violation"/"compliance".
    """
    stripped = raw.strip()
    if not stripped:
        return "skip"
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError:
        return "skip"
    if not isinstance(obj, dict):
        return "skip"  # valid JSON but not an object (a bare list/number)
    t = obj.get("t")
    key = (obj.get("p"), obj.get("file"), obj.get("line"), t)
    if key in seen:
        return "duplicate"
    seen.add(key)
    if t not in ("violation", "compliance"):
        # Non-finding rows (e.g. the file_done markers the pool appends)
        # still occupy a dedup key but classify as neither.
        return "skip"
    # Mirror parse_jsonl_line: `p` wins, `req` is the fallback.
    if resolver is not None and resolver.resolve(obj.get("p") or obj.get("req")) is None:
        return "quarantined"
    if t == "violation":
        if suppressed is not None and suppressed(obj):
            return "suppressed"
        return "violation"
    return "compliance"


def tally_unique_findings(
    jsonl_path: Path,
    suppressed: "Callable[[dict], bool] | None" = None,
    resolver: PrincipleResolver | None = None,
) -> FindingTally:
    """Count unique findings (deduplicated by ``(p, file, line, t)``) and duplicates.

    Single source of truth for the heartbeat and the dashboard progress reader,
    so the terminal and UI never disagree mid-batch — before the on-disk
    :func:`~quodeq.analysis.subagents.jsonl_utils.deduplicate_jsonl` pass runs
    at end of pool, the file holds raw appends from many parallel agents and
    contains overlapping findings.

    Two independent exclusions (*resolver*, *suppressed*) bring this in line
    with the report, both applied AFTER dedup so a row excluded three times
    counts once -- see :func:`_classify_finding_row` for how each row is
    classified and how the two exclusions interact.

    Tolerant: missing files, malformed lines, and OSError yield empty/partial
    tallies silently.
    """
    if not jsonl_path.is_file():
        return FindingTally()
    seen: set[tuple] = set()
    violations = compliance = duplicates = hidden = quarantined = 0
    try:
        with open_text(jsonl_path) as f:
            for raw in f:
                kind = _classify_finding_row(
                    raw, seen, suppressed=suppressed, resolver=resolver,
                )
                if kind == "duplicate":
                    duplicates += 1
                elif kind == "quarantined":
                    quarantined += 1
                elif kind == "suppressed":
                    hidden += 1
                elif kind == "violation":
                    violations += 1
                elif kind == "compliance":
                    compliance += 1
    except OSError:
        pass
    return FindingTally(
        violations=violations, compliance=compliance,
        duplicates=duplicates, suppressed=hidden, quarantined=quarantined,
    )
