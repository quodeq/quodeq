"""Shipped numeric thresholds in the maintainability standard.

The defaults are a product decision (2026-09-17: 6 parameters, 60-line
functions, 300-line files, cyclomatic complexity 15, matching what teams
run in detekt/ESLint), so a change here must be deliberate. The compiled
copy is generated from the source; the two drifting apart would ship one
number in the UI and another to the evaluator. CISQ reference names that
sit next to a parameterized rule must not repeat a number of their own, or
they contradict the default and every per-project override.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STANDARDS = REPO_ROOT / "src" / "quodeq" / "data" / "standards"

EXPECTED_MAINTAINABILITY_DEFAULTS = {
    ("M-MOD-1", "max_complexity"): 15,
    ("M-MOD-4", "max_params"): 6,
    ("M-MOD-7", "max_inheritance_depth"): 4,
    ("M-ANA-1", "max_file_lines"): 300,
    ("M-ANA-2", "max_lines"): 60,
    ("M-ANA-3", "max_depth"): 4,
}


def _requirements(data: object) -> list[dict]:
    """Every dict with an ``id`` and ``text`` anywhere in a standards document."""
    found: list[dict] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if "id" in node and "text" in node:
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return found


def _param_defaults(path: Path) -> dict[tuple[str, str], int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        (req["id"], name): spec["default"]
        for req in _requirements(data)
        for name, spec in (req.get("params") or {}).items()
    }


def test_maintainability_defaults_are_the_decided_values():
    defaults = _param_defaults(STANDARDS / "iso25010" / "maintainability.json")
    assert defaults == EXPECTED_MAINTAINABILITY_DEFAULTS


def test_compiled_params_match_source_for_every_dimension():
    for source in sorted((STANDARDS / "iso25010").glob("*.json")):
        compiled = STANDARDS / "compiled" / source.name
        if not compiled.exists():
            continue
        assert _param_defaults(compiled) == _param_defaults(source), (
            f"{compiled.relative_to(REPO_ROOT)} is stale; run "
            f"`uv run python tools/compile_standards.py --standards-dir {STANDARDS.relative_to(REPO_ROOT)} "
            f"--output-dir {(STANDARDS / 'compiled').relative_to(REPO_ROOT)}`"
        )


def test_cisq_names_beside_parameterized_rules_carry_no_number():
    source = json.loads((STANDARDS / "iso25010" / "maintainability.json").read_text(encoding="utf-8"))
    cisq = json.loads((STANDARDS / "cisq" / "maintainability.json").read_text(encoding="utf-8"))
    cisq_by_cwe = {entry["id"]: entry["requirement"] for entry in cisq.get("cwes", [])}
    offenders = []
    for req in _requirements(source):
        if not req.get("params"):
            continue
        for cwe in req.get("cwe") or []:
            text = cisq_by_cwe.get(cwe)
            if text and re.search(r"\d", text):
                offenders.append((req["id"], cwe, text))
    assert offenders == [], f"CISQ names hardcode a threshold next to a parameterized rule: {offenders}"
