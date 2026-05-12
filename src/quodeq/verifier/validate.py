"""Citation validation + self-consistency checks for verifier responses."""

from __future__ import annotations

import re
from dataclasses import replace

from quodeq.verifier.models import (
    ChecklistAnswer,
    VerifierResponse,
)


_FILE_LINE_RE = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+)$")


def _parse_cite(cite: str | None) -> tuple[str, int] | None:
    if not cite:
        return None
    if cite == "MANIFEST":
        return None
    m = _FILE_LINE_RE.match(cite)
    if not m:
        return None
    return (m.group("file"), int(m.group("line")))


def citations_resolvable(
    response: VerifierResponse, visible_lines: set[tuple[str, int]]
) -> list[str]:
    """Return a list of human-readable descriptions of invalid citations.

    A citation is valid if:
    - it is None (no claim), OR
    - it is the literal string "MANIFEST", OR
    - it parses as `file:line` AND `(file, line)` is in `visible_lines`.
    """
    invalid: list[str] = []
    for qid, ans in response.checklist.items():
        if ans.cite is None or ans.cite == "MANIFEST":
            continue
        parsed = _parse_cite(ans.cite)
        if parsed is None or parsed not in visible_lines:
            invalid.append(f"{qid}: cite {ans.cite!r} not in evidence")

    return invalid


def enforce_citation_validity(
    response: VerifierResponse, visible_lines: set[tuple[str, int]]
) -> VerifierResponse:
    """Return a copy of `response` with invalid-cite checklist answers downgraded
    to `unknown` and their cite set to `None`."""
    new_checklist: dict[str, ChecklistAnswer] = {}
    for qid, ans in response.checklist.items():
        if ans.cite is None or ans.cite == "MANIFEST":
            new_checklist[qid] = ans
            continue
        parsed = _parse_cite(ans.cite)
        if parsed is None or parsed not in visible_lines:
            new_checklist[qid] = ChecklistAnswer(answer="unknown", cite=None)
        else:
            new_checklist[qid] = ans
    return replace(response, checklist=new_checklist)


def self_consistency_warnings(response: VerifierResponse) -> list[str]:
    """DEPRECATED: Removed in Task 5. Function depended on findings block removed in Task 3.
    Task 6 will remove this stub and its call site in verifier.py."""
    return []
