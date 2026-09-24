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
import re

from pydantic import BaseModel, Field, field_validator

from quodeq.core.types.finding_type import FindingType, parse_finding_type
from quodeq.core.types.severity import Severity, parse_severity

SYSTEM_PROMPT = (
    "You are a code quality evaluator. Quote the offending code into "
    "`snippet` VERBATIM from the source, one or a few contiguous lines, "
    "exact characters, no paraphrase. Set `end_line` to match the last "
    "line of the snippet. In `reason`, state what the code does wrong and "
    "the concrete impact in 1 to 3 sentences. "
    'Return JSON as {"findings": [...]}; an empty array is valid.'
)


class _Finding(BaseModel):
    req: str = Field(description="Requirement ID (e.g. P-TIM-1, S-CON-3)")
    t: FindingType = Field(description="violation or compliance")
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
    severity: Severity = Field(default=Severity.MINOR)
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

    @field_validator("severity", mode="before")
    @classmethod
    def _coerce_unknown_severity(cls, value: object) -> object:
        """Fall back to the default severity instead of failing the whole finding.

        Local models mirror the finding *type* into this slot on compliance
        findings (``"t": "compliance"`` alongside ``"severity": "compliance"``),
        because the prompt marks severity required while offering only
        violation-shaped values. Severity is not one of the grounding fields
        #305 tightened -- it is optional here, with a default -- so an
        unreadable value carries no less information than an absent one.
        Discarding a finding whose ``snippet``, ``line`` and ``reason`` are
        sound over this field loses grounded evidence for nothing.

        Case and surrounding space are normalised on the way through, so
        ``"Major"`` lands as ``major`` rather than silently degrading to the
        default. Non-string input (``null``, a number) is the default too.
        """
        return parse_severity(value) if isinstance(value, str) else Severity.MINOR

    @field_validator("t", mode="before")
    @classmethod
    def _normalise_finding_type(cls, value: object) -> object:
        """Land ``"Violation"`` or ``" compliance "`` on the canonical type.

        Case and surrounding space are model noise, like severity's. Any
        other value (``"violations"``, a list) passes through unchanged so the
        enum still rejects it and the finding counts as dropped.
        """
        return parse_finding_type(value) or value


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
_MIN_FINDING_FIELD_OVERLAP = 2  # one shared short key (t/w) alone is not a finding attempt


def _looks_like_finding(node: dict) -> bool:
    """True if *node* shares enough keys with the finding schema to be a finding
    attempt rather than a generic container. Two-field floor avoids false
    positives from generic short keys like ``t``/``w`` appearing alone.
    """
    return len(_FINDING_FIELDS.intersection(node)) >= _MIN_FINDING_FIELD_OVERLAP


_UNKNOWN_DROP_REASON = "unknown:unknown"


def _record_drop_reason(exc: Exception, reasons: dict[str, int] | None) -> None:
    """Tally *exc*'s failing ``field:error_type`` pairs into *reasons*.

    The count alone says a finding was discarded but never which constraint
    rejected it, which left a systemic output-shape problem only diagnosable
    by replaying prompts against the model. Pydantic's ``ValidationError``
    already carries the per-field verdict; this lifts it into a histogram the
    caller can log. Non-pydantic failures (``KeyError``, ``TypeError``) have
    no such detail and land under a single bucket.
    """
    if reasons is None:
        return
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        reasons[_UNKNOWN_DROP_REASON] = reasons.get(_UNKNOWN_DROP_REASON, 0) + 1
        return
    for err in errors():
        field = ".".join(str(part) for part in err.get("loc", ())) or "unknown"
        key = f"{field}:{err.get('type', 'unknown')}"
        reasons[key] = reasons.get(key, 0) + 1


def _extract_finding_dicts(
    node: object,
    sink: list[dict],
    dropped: list[dict],
    reasons: dict[str, int] | None = None,
) -> None:
    """Walk a decoded JSON value, appending any dict that parses as a `_Finding`.

    Recovers findings whether the model emitted them as a bare object, a list,
    a wrapped ``{"findings": [...]}``, or nested somewhere unexpected. Recursion
    stops at a successful ``_Finding`` validation. A dict that fails validation
    but is a finding attempt (carries ``req`` or otherwise looks like a finding)
    is counted as dropped, then recursion stops (mirroring the valid path). Pure
    containers (no finding-like keys) are recursed to recover nested findings.

    *reasons*, when supplied, accumulates a ``field:error_type`` histogram of
    why each dropped finding failed, for the caller to log.
    """
    if isinstance(node, dict):
        try:
            f = _Finding.model_validate(node)
            sink.append(f.model_dump())
            return
        except (ValueError, KeyError, TypeError) as exc:
            # A finding-shaped LEAF (shares finding fields, no nested containers)
            # that failed validation is a malformed finding attempt -> count it.
            # A dict that merely shares field names while NESTING dicts/lists is a
            # wrapper: fall through and recurse so its real findings are recovered
            # rather than swallowed (counting + stopping here would lose them).
            has_nested = any(isinstance(v, (dict, list)) for v in node.values())
            if _DROPPED_FINDING_KEY in node or (_looks_like_finding(node) and not has_nested):
                dropped.append(node)
                _record_drop_reason(exc, reasons)
                return
        for value in node.values():
            _extract_finding_dicts(value, sink, dropped, reasons)
    elif isinstance(node, list):
        for item in node:
            _extract_finding_dicts(item, sink, dropped, reasons)


# Next JSON opener at or after a position. One search per hop keeps the walk
# linear in len(raw_json): every search starts past the previous candidate, so
# no stretch is scanned twice. Two separate str.find calls re-scanned up to the
# far bracket after every failed decode, which went quadratic on output with
# many stray openers.
_JSON_OPENER_RE = re.compile(r"[\[{]")


def parse_findings(
    raw_json: str,
    *,
    drop_reasons: dict[str, int] | None = None,
    dropped_sink: list[dict] | None = None,
) -> tuple[list[dict], int]:
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
    Pass *drop_reasons* to also collect a ``field:error_type`` histogram naming
    which constraint rejected each one; the caller logs it, since this module
    sits inside the SEP-06 no-logging boundary. Pass *dropped_sink* to also
    receive the rejected dicts themselves, so the caller can attempt a repair
    re-ask instead of only counting the loss.
    """
    decoder = json.JSONDecoder()
    findings: list[dict] = []
    dropped: list[dict] = dropped_sink if dropped_sink is not None else []
    i = 0
    while (opener := _JSON_OPENER_RE.search(raw_json, i)) is not None:
        start = opener.start()
        try:
            node, end = decoder.raw_decode(raw_json, start)
        except json.JSONDecodeError:
            i = start + 1
            continue
        _extract_finding_dicts(node, findings, dropped, drop_reasons)
        i = end
    return findings, len(dropped)
