"""Serialization-boundary ratchet: to_camel_dict belongs at wire boundaries.

``to_camel_dict`` produces the JSON wire format. The HTTP routes in ``api/``
are the canonical wire boundary; every other use must be a DECLARED boundary
listed below with its reason. The test fails when a new undeclared use
appears (fix: serialize at the route instead) and when a declared file no
longer uses it (fix: delete the entry — the list only shrinks).
"""
from __future__ import annotations

from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent.parent / "src" / "quodeq"

# Relative to src/quodeq. Every entry is a wire boundary that is NOT an HTTP
# route, with the reason it serializes. Burn-down candidates are marked.
DECLARED_WIRE_BOUNDARIES: dict[str, str] = {
    "core/types/_serialization.py": "defines the serializer",
    "core/types/__init__.py": "re-exports the serializer",
    "assistant/tools/_read_tools.py": "assistant tool output is its own wire (LLM-facing)",
    "analysis/_report_scoring.py": "dimension report files on disk are camelCase (stored contract)",
    "data/fs/report_parser/_eval_parsing.py": "parses stored camelCase findings back out (stored contract)",
    "services/accumulated.py": "payload feeds both routes and the persisted score cache — burn-down: WS5/scoring reader",
    "services/rescore.py": "envelope consumed by routes AND services/scoring — burn-down: WS5/scoring reader",
    "services/_dashboard_response.py": "run-dim LRU stores wire payloads — burn-down: WS5/scoring reader",
    "services/_fs_reports.py": "violation responses cached in wire shape — burn-down: WS5",
    "services/scoring/_response_builders.py": "scoring payloads flow into SSE + caches in wire shape — burn-down: WS5/scoring reader",
}


def _files_using_to_camel_dict() -> set[str]:
    out: set[str] = set()
    for py in SRC_ROOT.rglob("*.py"):
        rel = py.relative_to(SRC_ROOT).as_posix()
        if rel.startswith("api/"):
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "to_camel_dict" in text:
            out.add(rel)
    return out


def test_no_undeclared_serialization_outside_routes():
    used = _files_using_to_camel_dict()
    undeclared = sorted(used - set(DECLARED_WIRE_BOUNDARIES))
    assert undeclared == [], (
        "to_camel_dict used outside api/ in undeclared file(s). Serialize at "
        "the route instead, or (only for a genuine non-HTTP wire boundary) "
        "add a declared entry with its reason:\n" + "\n".join(undeclared)
    )


def test_declared_boundaries_are_not_stale():
    used = _files_using_to_camel_dict()
    stale = sorted(set(DECLARED_WIRE_BOUNDARIES) - used)
    assert stale == [], (
        "Declared wire boundaries no longer use to_camel_dict — delete their "
        "entries (the list only shrinks):\n" + "\n".join(stale)
    )
