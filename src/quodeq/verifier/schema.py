"""JSON Schema for the verifier's model response.

Used by:
- Ollama's `format` parameter to enforce structural correctness at decode time.
- The response parser to validate model output before passing it downstream.
"""

from __future__ import annotations

from typing import Any


def _answer_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer", "cite"],
        "properties": {
            "answer": {"type": "string", "enum": ["yes", "no", "unknown"]},
            "cite": {"type": ["string", "null"]},
        },
    }


def _finding_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["value", "cite"],
        "properties": {
            "value": {"type": ["string", "null"]},
            "cite": {"type": ["string", "null"]},
        },
    }


RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["checklist", "findings", "confidence", "evidence_summary"],
    "properties": {
        "checklist": {
            "type": "object",
            "additionalProperties": False,
            "required": ["Q1", "Q2", "Q3", "Q4", "Q5"],
            "properties": {q: _answer_schema() for q in ("Q1", "Q2", "Q3", "Q4", "Q5")},
        },
        "findings": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "default_implementation",
                "override_mechanism",
                "abstraction_in_use",
            ],
            "properties": {
                "default_implementation": _finding_schema(),
                "override_mechanism": _finding_schema(),
                "abstraction_in_use": _finding_schema(),
            },
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "evidence_summary": {"type": "string", "maxLength": 200},
    },
}
