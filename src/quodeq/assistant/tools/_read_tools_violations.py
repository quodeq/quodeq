"""Violation shaping and paging for the read tools: trimming to the
model-facing shape, principle/requirement/severity normalization across the
run-scoped and accumulated payload shapes, hidden-standard filtering, and
get_violations' scope routing.
"""
from __future__ import annotations

import json

from quodeq.assistant.tools import _read_tools as _facade
from quodeq.assistant.tools import _read_tools_scope as _scope_facade
from quodeq.assistant.tools._context import ToolContext
from quodeq.assistant.tools._registry import ToolError
from quodeq.core.standards.visibility import (
    hidden_ids_for_names,
    partition_entries_visible,
    partition_visible,
)

# Trimmed violation shape shared by get_report and get_violations. We keep only
# the fields that let the model locate and explain an issue and DROP the large
# `snippet`/`context` blobs so a report full of violations stays within a sane
# context budget. Use search_findings when the model needs the code snippet.
_VIOLATION_FIELDS = ("principle", "file", "line", "severity", "title", "reason")
# get_violations paging limits.
_VIOLATIONS_DEFAULT_LIMIT = 40
_VIOLATIONS_MAX_LIMIT = 100
# Severity ordering (critical/major first). Unknown severities sort last.
_SEVERITY_RANK = {
    "critical": 0, "blocker": 0, "high": 1, "major": 1,
    "moderate": 2, "medium": 2, "minor": 3, "low": 3, "info": 4, "trivial": 4,
}


def _available_names(ctx: ToolContext, dims: list[dict]) -> str:
    """Comma-joined visible dimension names for a not-found error message.

    Filtered so an error never discloses a dimension the user has hidden.
    """
    names = [d.get("dimension") for d in dims if d.get("dimension")]
    shown, _ = partition_visible(names, ctx.visible_standard_ids)
    return ", ".join(sorted(shown))


def _hidden_ids(ctx: ToolContext, names: list[str]) -> list[str]:
    """Which of *names* the user has hidden. See ``hidden_ids_for_names``."""
    return hidden_ids_for_names(names, ctx.visible_standard_ids)


def _visible_only(ctx: ToolContext, entries: list[dict],
                  key: str = "dimension") -> tuple[list[dict], list[str]]:
    """Drop entries whose dimension the user has hidden.

    Thin per-context wrapper around ``partition_entries_visible`` -- the one
    shared implementation used by every read surface, including
    ``_overview.get_overview``, so "what counts as hidden" cannot drift
    between them.
    """
    return partition_entries_visible(entries, ctx.visible_standard_ids, key=key)


def _principle_of(v: dict):
    # Run-scoped eval JSON keys the principle as "principle"; the accumulated
    # payload (serialized Finding) keys it as "practiceId". Accept either so
    # one trim/sort works for both scopes.
    return v.get("principle") or v.get("practiceId")


def _requirement_of(v: dict) -> str:
    # The requirement id (Finding.req) is the FIRST element of the (req, file,
    # line) identity that dismiss/verify and the suppression filter key on.
    # Run-scoped eval JSON and the accumulated serialized-Finding payload both
    # key it as "req"; accept "requirement" too for any producer that already
    # renamed it. Often absent (req is optional; practiceId is the guaranteed
    # identity), so it is normalized to "" rather than None so it round-trips
    # as a valid dismiss key.
    return str(v.get("req") or v.get("requirement") or "")


def _coerce_line(line) -> int:
    # dismiss keys store line as int; Finding.line is typed int|str|None. Coerce
    # so a string line ("5") still matches a stored int line (5).
    try:
        return int(line)
    except (TypeError, ValueError):
        return 0


def _trim_violation(v: dict) -> dict:
    out = {k: v.get(k) for k in _VIOLATION_FIELDS}
    out["principle"] = _principle_of(v)
    # Expose the requirement id so the model can form a correct dismiss/verify
    # key. Without it, get_report/get_violations only surfaced `principle`, and
    # a dismiss drafted from that data carried a wrong/empty req that never
    # matched the finding on the suppression read path (silent no-op).
    out["requirement"] = _requirement_of(v)
    return out


def _severity_key(v: dict):
    sev = (v.get("severity") or "").lower()
    return (_SEVERITY_RANK.get(sev, 99), _principle_of(v) or "")


def _get_violations(ctx: ToolContext, dimension: str | None = None,
                    limit: int = _VIOLATIONS_DEFAULT_LIMIT) -> dict:
    limit = max(1, min(int(limit), _VIOLATIONS_MAX_LIMIT))
    if _scope_facade._has_run(ctx):
        raw, dim_out, hidden = _violations_from_run(ctx, dimension)
    else:
        raw, dim_out, hidden = _violations_from_accumulated(ctx, dimension)

    # by_principle counts reflect ALL violations so "worst principle" stays
    # accurate even when the returned list is capped by `limit`.
    by_principle: dict[str, int] = {}
    for v in raw:
        key = _principle_of(v) or "(unknown)"
        by_principle[key] = by_principle.get(key, 0) + 1

    ordered = sorted(raw, key=_severity_key)
    trimmed = [_trim_violation(v) for v in ordered[:limit]]
    return {"dimension": dim_out, "count": len(raw), "violations": trimmed,
            "by_principle": by_principle, "hiddenStandardIds": hidden}


def _violations_from_run(ctx: ToolContext, dimension: str | None):
    eval_dir = ctx.run_dir / "evaluation"
    if dimension:
        _facade._validate_dimension(dimension)
        path = eval_dir / f"{dimension}.json"
        if not path.is_file():
            raise ToolError(
                f"no report for dimension: {dimension} in this run. "
                "Check get_scores for available dimensions, or get_overview "
                "for accumulated scores across runs.")
        scored = _scope_facade._scored_run_dims(ctx)
        if scored is not None:
            entry = next((d for d in scored if d.get("dimension") == dimension), None)
            if entry is not None:
                return entry.get("violations") or [], dimension, []
        viols = json.loads(path.read_text(encoding="utf-8")).get("violations") or []
        return viols, dimension, []
    if not eval_dir.is_dir():
        raise ToolError(
            "no evaluation reports in this run. Try get_overview for "
            "accumulated scores across runs.")
    scored = _scope_facade._scored_run_dims(ctx)
    if scored is None:
        scored = _facade._raw_run_dims(eval_dir)
    kept, hidden = _visible_only(ctx, scored)
    return [v for d in kept for v in (d.get("violations") or [])], None, hidden


def _violations_from_accumulated(ctx: ToolContext, dimension: str | None):
    dims = _scope_facade._accumulated_dims(ctx)
    if dims is None:
        raise _scope_facade._no_scope_error()
    if dimension:
        entry = next((d for d in dims if d.get("dimension") == dimension), None)
        if entry is None:
            avail = _available_names(ctx, dims)
            raise ToolError(
                f"no report for dimension: {dimension}. Available: "
                f"{avail or '(none)'}. Or try get_overview for accumulated scores.")
        return entry.get("violations") or [], dimension, []
    kept, hidden = _visible_only(ctx, dims)
    raw: list = []
    for d in kept:
        raw.extend(d.get("violations") or [])
    return raw, None, hidden
