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

    for fname, fext in _findings_items(response):
        if fext.cite is None or fext.cite == "MANIFEST":
            continue
        parsed = _parse_cite(fext.cite)
        if parsed is None or parsed not in visible_lines:
            invalid.append(f"findings.{fname}: cite {fext.cite!r} not in evidence")

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
    """Return a list of warnings where the structured findings contradict
    the checklist answers."""
    warnings: list[str] = []
    cl = response.checklist
    f = response.findings

    if f.override_mechanism.value and cl["Q5"].answer != "yes":
        warnings.append("findings.override_mechanism is non-null but Q5 != yes")
    if f.abstraction_in_use.value and cl["Q4"].answer != "yes":
        warnings.append("findings.abstraction_in_use is non-null but Q4 != yes")
    if f.default_implementation.value and cl["Q2"].answer not in ("yes", "unknown"):
        warnings.append("findings.default_implementation is non-null but Q2 == no")

    return warnings


def _findings_items(response: VerifierResponse):
    yield "default_implementation", response.findings.default_implementation
    yield "override_mechanism", response.findings.override_mechanism
    yield "abstraction_in_use", response.findings.abstraction_in_use
