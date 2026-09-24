"""The rubric's fault-isolation carve-out for generic catches (R-FT-7).

The reliability dimension files every generic catch, including ones at real
isolation boundaries (worker thread entry, one queue iteration, a plugin
callback) that log with a traceback. The carve-out must stay narrow: ordinary
logic, a sub-warning log, a dropped traceback, or continuing with partial state
all remain violations.
"""
from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "src" / "quodeq" / "data" / "prompts"
RULES = (_PROMPTS_DIR / "evaluation_rules.md").read_text(encoding="utf-8")


def _not_a_violation_line() -> str:
    lines = [line for line in RULES.splitlines() if line.startswith("NOT a violation:")]
    assert len(lines) == 1, "expected exactly one 'NOT a violation:' line"
    return lines[0].lower()


def test_carve_out_names_the_boundary_kinds() -> None:
    line = _not_a_violation_line()
    assert "fault-isolation boundary" in line
    assert "thread or task entry point" in line
    assert "event loop or work queue" in line
    assert "third-party or plugin callback" in line


def test_carve_out_requires_traceback_at_warning_or_above() -> None:
    line = _not_a_violation_line()
    assert "stack trace" in line
    assert "warning level or above" in line


def test_carve_out_keeps_ordinary_logic_a_violation() -> None:
    line = _not_a_violation_line()
    assert "partially-updated state" in line
    assert "around ordinary logic" in line
    assert "r-ft-7" in line
