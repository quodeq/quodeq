"""JSON Schema for the verifier model response (v8).

The response contains:
  - checklist: four questions (Q1-Q4), each with answer + cite.
  - confidence: model-reported confidence in [0, 1].
  - evidence_summary: short forensic string the audit log retains.

No structured `findings` block (that was v7.2 substitutability-only).
The verdict is computed deterministically Python-side, not emitted by the
model — see verdict.py.
"""

from __future__ import annotations


def _checklist_entry() -> dict:
    return {
        "type": "object",
        "required": ["answer", "cite"],
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string", "enum": ["yes", "no", "unknown"]},
            "cite": {"type": ["string", "null"]},
        },
    }


RESPONSE_SCHEMA: dict = {
    "type": "object",
    "required": ["checklist", "confidence", "evidence_summary"],
    "additionalProperties": False,
    "properties": {
        "checklist": {
            "type": "object",
            "required": ["Q1", "Q2", "Q3", "Q4"],
            "additionalProperties": False,
            "properties": {
                q: _checklist_entry() for q in ("Q1", "Q2", "Q3", "Q4")
            },
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        # Bounded so a chatty model can't bloat the audit log. 500 chars
        # comfortably fits the 2-3 sentence summaries the v8 worked example
        # demonstrates; v7.2's 200-char cap truncated mid-word in practice.
        "evidence_summary": {"type": "string", "maxLength": 500},
    },
}
