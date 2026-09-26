"""Classify one run's findings against a previous run's by identity.

Identity is the fingerprinted dismiss key: requirement, file and the
whitespace-normalised snippet hash, falling back to the line when the
snippet is blank. Counting by identity is what lets two runs be compared
when a fresh pass surfaces a different sample of the same problems.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace

from quodeq.core.finding_identity import coerce_line, snippet_fingerprint
from quodeq.core.finding_markers import CARRIED_FORWARD
from quodeq.core.types.severity import Severity

_BLOCKING = frozenset({Severity.CRITICAL, Severity.MAJOR})


@dataclass(frozen=True)
class RunDiff:
    """Every current finding lands in exactly one of carried / same / moved /
    new; every previous finding in same / moved / resolved / not_reevaluated."""

    carried: list[dict] = field(default_factory=list)
    same: list[dict] = field(default_factory=list)
    moved: list[dict] = field(default_factory=list)
    new: list[dict] = field(default_factory=list)
    resolved: list[dict] = field(default_factory=list)
    not_reevaluated: list[dict] = field(default_factory=list)
    types_closed: list[str] = field(default_factory=list)
    types_opened: list[str] = field(default_factory=list)
    per_req: dict[str, tuple[int, int]] = field(default_factory=dict)
    majors_delta: int = 0


def identity(finding: dict) -> tuple:
    """``(req, file, fingerprint)``, or ``(req, file, line)`` for a blank snippet."""
    req = str(finding.get("req") or "")
    file = str(finding.get("file") or "")
    fp = snippet_fingerprint(req, finding.get("snippet"))
    return (req, file, fp) if fp else (req, file, coerce_line(finding.get("line")))


def _content_key(finding: dict) -> tuple | None:
    """``(req, fingerprint)`` without the file, for detecting a move."""
    req = str(finding.get("req") or "")
    fp = snippet_fingerprint(req, finding.get("snippet"))
    return (req, fp) if fp else None


def _blocking(findings: list[dict]) -> int:
    return sum(1 for f in findings if f.get("severity") in _BLOCKING)


def _classify_current(diff: RunDiff, current: list[dict], prev_ids: set, prev_content: set) -> None:
    for f in current:
        if f.get(CARRIED_FORWARD):
            diff.carried.append(f)
        elif identity(f) in prev_ids:
            diff.same.append(f)
        elif (k := _content_key(f)) and k in prev_content:
            diff.moved.append(f)
        else:
            diff.new.append(f)


def _classify_previous(
    diff: RunDiff, previous: list[dict], curr_ids: set, curr_content: set, current_files: set[str],
) -> None:
    for f in previous:
        if identity(f) in curr_ids:
            continue
        if (k := _content_key(f)) and k in curr_content:
            continue
        bucket = diff.resolved if str(f.get("file") or "") in current_files else diff.not_reevaluated
        bucket.append(f)


def diff_findings(previous: list[dict], current: list[dict], *, current_files: set[str]) -> RunDiff:
    """Classify *current* against *previous*; *current_files* is every file the
    current run read (any violation or compliance names it)."""
    diff = RunDiff()
    _classify_current(
        diff, current, {identity(f) for f in previous},
        {k for f in previous if (k := _content_key(f))},
    )
    _classify_previous(
        diff, previous, {identity(f) for f in current},
        {k for f in current if (k := _content_key(f))}, current_files,
    )
    prev_reqs = Counter(str(f.get("req") or "") for f in previous)
    curr_reqs = Counter(str(f.get("req") or "") for f in current)
    for req in sorted(prev_reqs.keys() | curr_reqs.keys()):
        diff.per_req[req] = (prev_reqs[req], curr_reqs[req])
    diff.types_closed.extend(r for r in sorted(prev_reqs) if r not in curr_reqs)
    diff.types_opened.extend(r for r in sorted(curr_reqs) if r not in prev_reqs)
    return replace(diff, majors_delta=_blocking(current) - _blocking(previous))
