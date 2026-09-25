"""Live evidence tally: unique finding counts from a dim's raw evidence jsonl.

Single source of truth for the subagent-pool heartbeat and the dashboard's
live scan-progress reader, so the terminal and UI never disagree mid-batch --
before the on-disk deduplication pass runs at end of pool, the file holds raw
appends from many parallel agents and contains overlapping findings.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Callable

from quodeq.core.evidence.req_mapping import PrincipleResolver
from quodeq.core.types.finding_type import FINDING_TYPES, FindingType
from quodeq.shared.utils import open_text

_logger = logging.getLogger(__name__)


class _RowClass(StrEnum):
    """_classify_finding_row's non-finding-type outcomes (see its docstring).

    A finding row classifies as one of these, or as FindingType.VIOLATION /
    FindingType.COMPLIANCE.
    """

    SKIP = "skip"
    DUPLICATE = "duplicate"
    QUARANTINED = "quarantined"
    SUPPRESSED = "suppressed"


# The row classes a tally counts, one counter each.
_COUNTED_KINDS = (
    FindingType.VIOLATION, FindingType.COMPLIANCE,
    _RowClass.DUPLICATE, _RowClass.SUPPRESSED, _RowClass.QUARANTINED,
)


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
        """Unique findings of either kind. Excludes duplicates and both exclusions."""
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
    :func:`~quodeq.core.evidence.req_mapping.group_judgments`. *suppressed*
    (see ``quodeq.services.suppression``, injected to keep this module free
    of a services dependency) classifies "suppressed" a violation the user
    already dismissed or deleted. Quarantine is checked first: a finding
    with no principle in the standard has no valid delete key, so asking
    whether it was suppressed is not meaningful. Without either argument,
    every finding classifies as "violation"/"compliance".
    """
    stripped = raw.strip()
    if not stripped:
        return _RowClass.SKIP
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError:
        return _RowClass.SKIP
    if not isinstance(obj, dict):
        return _RowClass.SKIP  # valid JSON but not an object (a bare list/number)
    t = obj.get("t")
    key = (obj.get("p"), obj.get("file"), obj.get("line"), t)
    if key in seen:
        return _RowClass.DUPLICATE
    seen.add(key)
    if t not in FINDING_TYPES:
        # Non-finding rows (e.g. the file_done markers the pool appends)
        # still occupy a dedup key but classify as neither.
        return _RowClass.SKIP
    # Mirror parse_jsonl_line: `p` wins, `req` is the fallback.
    if resolver is not None and resolver.resolve(obj.get("p") or obj.get("req")) is None:
        return _RowClass.QUARANTINED
    if t == FindingType.VIOLATION:
        if suppressed is not None and suppressed(obj):
            return _RowClass.SUPPRESSED
        return FindingType.VIOLATION
    return FindingType.COMPLIANCE


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
    counts = _zero_counts()
    try:
        with open_text(jsonl_path) as f:
            for raw in f:
                kind = _classify_finding_row(
                    raw, seen, suppressed=suppressed, resolver=resolver,
                )
                if kind in counts:
                    counts[kind] += 1
    except OSError as exc:
        _logger.debug("evidence file unreadable during tally: %s", exc)
    return _tally_of(counts)


def _zero_counts() -> dict[str, int]:
    """A zero counter per counted row class (SKIP is not counted)."""
    return dict.fromkeys(_COUNTED_KINDS, 0)


def _tally_of(counts: dict[str, int]) -> FindingTally:
    """The FindingTally for *counts* (see ``_zero_counts``)."""
    return FindingTally(
        violations=counts[FindingType.VIOLATION], compliance=counts[FindingType.COMPLIANCE],
        duplicates=counts[_RowClass.DUPLICATE], suppressed=counts[_RowClass.SUPPRESSED],
        quarantined=counts[_RowClass.QUARANTINED],
    )


_TAIL_GUARD = 512


class IncrementalTally:
    """A ``tally_unique_findings`` that resumes where its last call stopped.

    The evidence jsonl is append-only while a pool runs, so each call reads
    the bytes appended since the previous one and folds them into the same
    dedup set and counters. Only complete lines are consumed: a trailing
    partial line (an agent mid-write) waits for the next call. The consumed
    tail is remembered; when the file is shorter than the offset or the tail
    no longer matches (the end-of-pool dedup pass rewrites the file in
    place), everything is re-read from zero.
    """

    def __init__(
        self, path: Path, *,
        suppressed: "Callable[[dict], bool] | None" = None,
        resolver: PrincipleResolver | None = None,
    ) -> None:
        self.path = path
        self._suppressed = suppressed
        self._resolver = resolver
        self._reset()

    def _reset(self) -> None:
        self.offset = 0
        self._tail = b""
        self._seen: set[tuple] = set()
        self._counts = _zero_counts()

    def _tail_matches(self, f) -> bool:
        if not self._tail:
            return True
        f.seek(self.offset - len(self._tail))
        return f.read(len(self._tail)) == self._tail

    def advance(self) -> FindingTally:
        """Fold in the bytes appended since the last call and return the running tally.

        Safe to call on a partially written file and on one that does not exist
        yet. A shrink or a rewritten tail restarts the count from zero.
        """
        if not self.path.is_file():
            self._reset()
            return self._tally()
        try:
            with open(self.path, "rb") as f:
                size = f.seek(0, 2)
                if size < self.offset or not self._tail_matches(f):
                    self._reset()
                f.seek(self.offset)
                data = f.read()
        except OSError as exc:
            _logger.debug("evidence file unreadable during tally: %s", exc)
            return self._tally()
        end = data.rfind(b"\n")
        if end < 0:
            return self._tally()
        complete = data[: end + 1]
        for raw in complete.decode("utf-8", errors="replace").split("\n"):
            kind = _classify_finding_row(raw, self._seen, suppressed=self._suppressed, resolver=self._resolver)
            if kind in self._counts:
                self._counts[kind] += 1
        self.offset += len(complete)
        self._tail = complete[-_TAIL_GUARD:]
        return self._tally()

    def _tally(self) -> FindingTally:
        return _tally_of(self._counts)
