"""Pydantic schema for the API runner's structured LLM output, and the
lenient parser that recovers findings from malformed or partial JSON.

``_Finding`` is a lenient short-key variant of the canonical ``Judgment``
(``quodeq.core.events.models``). Local models drop required fields and balk
at long field names under load -- this type's short keys (``req``/``t``/``w``)
and Field descriptions are tuned for that constraint. The downstream wire-dict
→ Judgment lift happens via ``quodeq.core.finding_mappings.wire_dict_to_judgment``
after ``FindingEnricher`` maps ``req`` to ``practice_id``.
"""
from __future__ import annotations

import json
from enum import Enum as _Enum

from pydantic import BaseModel, Field

_SYSTEM_PROMPT = (
    "You are a code quality evaluator. Quote the offending code into "
    "`snippet` VERBATIM from the source, one or a few contiguous lines, "
    "exact characters, no paraphrase. Set `end_line` to match the last "
    "line of the snippet. In `reason`, state what the code does wrong and "
    "the concrete impact in 1 to 3 sentences. "
    'Return JSON as {"findings": [...]}; an empty array is valid.'
)


class _FindingType(str, _Enum):
    violation = "violation"
    compliance = "compliance"


class _Severity(str, _Enum):
    critical = "critical"
    major = "major"
    minor = "minor"


class _Finding(BaseModel):
    req: str = Field(description="Requirement ID (e.g. P-TIM-1, S-CON-3)")
    t: _FindingType = Field(description="violation or compliance")
    file: str = Field(description="File path relative to repo root")
    line: int = Field(description="1-indexed line number of the offending expression. MUST be > 0.", gt=0)
    end_line: int | None = Field(
        default=None,
        description=(
            "Last line of the offending span. Set this whenever the violation "
            "spans more than one line — both for structural issues (long "
            "function, nesting depth) and for multi-line expressions or "
            "blocks. Omit only when the issue is genuinely a single line. "
            "The server reads the actual source to render the highlighted "
            "snippet from line..end_line; getting end_line right is what "
            "makes the highlight readable."
        ),
    )
    severity: _Severity = Field(default=_Severity.minor)
    vt: str | None = Field(
        default=None,
        description=(
            "Violation type taxonomy code: a short, stable, kebab-case class "
            "of the violation (e.g. 'code-injection', 'hardcoded-secret', "
            "'missing-error-handling'). Reuse the exact same code for every "
            "finding of the same kind so near-duplicates group together."
        ),
    )
    w: str = Field(description="Short title of the finding")
    snippet: str = Field(
        description=(
            "Offending code copied VERBATIM from the source file — exact "
            "characters, no paraphrase, no summarisation. One or a few "
            "contiguous lines: quote enough that the issue is self-evident, "
            "no padding. The number of lines in `snippet` must match the "
            "span from `line` to `end_line` (so end_line - line + 1 == "
            "snippet line count). Required. If you cannot quote the code, "
            "drop the finding."
        ),
        min_length=1,
    )
    reason: str = Field(
        description=(
            "1–3 sentences: state what the quoted code does wrong AS WRITTEN, "
            "and name the concrete impact (what breaks, who is affected, or "
            "what attack/failure it enables). "
            "No hedging ('could', 'might', 'should consider', 'if X were larger')."
        ),
        min_length=1,
    )


# A dict that fails `_Finding` validation but carries the required, domain-specific
# `req` identifier is a *dropped finding* attempt: counted once for observability,
# then we stop (its own fields are not separate findings, mirroring the valid path).
# A dict that LOOKS like a finding (shares >=2 fields with the schema) but is missing
# `req` is also a dropped attempt -- BUT only when it is a leaf (no nested dict/list
# values). A dict that shares field names yet nests dicts/lists is treated as a
# wrapper and recursed into, so real findings inside it (e.g. {"findings": [...]}) are
# recovered rather than swallowed. The trade-off: a malformed, req-less finding that
# itself nests a container is recursed instead of counted, so it is not tallied in the
# (observability-only) dropped count -- acceptable, since a req-bearing attempt is
# still always counted regardless of nesting.
_DROPPED_FINDING_KEY = "req"
_FINDING_FIELDS = frozenset(_Finding.model_fields)


def _looks_like_finding(node: dict) -> bool:
    """True if *node* shares enough keys with the finding schema to be a finding
    attempt rather than a generic container. Two-field floor avoids false
    positives from generic short keys like ``t``/``w`` appearing alone.
    """
    return len(_FINDING_FIELDS.intersection(node)) >= 2


def _extract_finding_dicts(node: object, sink: list[dict], dropped: list[dict]) -> None:
    """Walk a decoded JSON value, appending any dict that parses as a `_Finding`.

    Recovers findings whether the model emitted them as a bare object, a list,
    a wrapped ``{"findings": [...]}``, or nested somewhere unexpected. Recursion
    stops at a successful ``_Finding`` validation. A dict that fails validation
    but is a finding attempt (carries ``req`` or otherwise looks like a finding)
    is counted as dropped, then recursion stops (mirroring the valid path). Pure
    containers (no finding-like keys) are recursed to recover nested findings.
    """
    if isinstance(node, dict):
        try:
            f = _Finding.model_validate(node)
            sink.append(f.model_dump())
            return
        except (ValueError, KeyError, TypeError):
            if _DROPPED_FINDING_KEY in node:
                dropped.append(node)
                return
            # A finding-shaped LEAF (shares finding fields, no nested containers)
            # that failed validation is a malformed finding attempt -> count it.
            # A dict that merely shares field names while NESTING dicts/lists is a
            # wrapper: fall through and recurse so its real findings are recovered
            # rather than swallowed (counting + stopping here would lose them).
            has_nested = any(isinstance(v, (dict, list)) for v in node.values())
            if _looks_like_finding(node) and not has_nested:
                dropped.append(node)
                return
        for value in node.values():
            _extract_finding_dicts(value, sink, dropped)
    elif isinstance(node, list):
        for item in node:
            _extract_finding_dicts(item, sink, dropped)


def _parse_findings(raw_json: str) -> tuple[list[dict], int]:
    """Parse findings from raw (possibly malformed) model output.

    This is the primary parser, not a fallback. Local models produce several
    failure shapes: bare finding objects concatenated without an array wrapper
    (``{...}{...}``); a complete ``{"findings": [...]}`` wrapper with hedging
    text around it; findings with nested fields like ``req_refs: [{...}]``.

    Strategy: walk the input with ``json.JSONDecoder().raw_decode()`` to find
    every complete top-level JSON value (bracket-aware, so nested structures
    pass through), then harvest anything that validates as a ``_Finding``.

    Returns ``(valid_findings, dropped_count)`` where *dropped_count* is the
    number of finding-shaped dicts that failed validation (for observability).
    """
    decoder = json.JSONDecoder()
    findings: list[dict] = []
    dropped: list[dict] = []
    i = 0
    n = len(raw_json)
    while i < n:
        brace = raw_json.find("{", i)
        bracket = raw_json.find("[", i)
        candidates = [c for c in (brace, bracket) if c >= 0]
        if not candidates:
            break
        start = min(candidates)
        try:
            node, end = decoder.raw_decode(raw_json, start)
        except json.JSONDecodeError:
            i = start + 1
            continue
        _extract_finding_dicts(node, findings, dropped)
        i = end
    return findings, len(dropped)
