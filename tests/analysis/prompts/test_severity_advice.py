"""The standard's suggested severity reaches the model on every checklist renderer."""
import json
from pathlib import Path

from quodeq.analysis.prompts.builder import render_compact_standards, render_compiled_standards
from quodeq.analysis.subprocess import render_standards_grouped
from quodeq.analysis.prompts.severity_advice import advised_severity
from quodeq.analysis.prompts.builder import load_evaluation_rules

COMPILED = Path(__file__).resolve().parents[3] / "src" / "quodeq" / "data" / "standards" / "compiled"


def test_advised_severity_reads_the_requirement():
    assert advised_severity({"id": "X", "severity": "major"}) == "major"


def test_advised_severity_ignores_junk():
    assert advised_severity({"id": "X", "severity": "huge"}) is None
    assert advised_severity({"id": "X"}) is None
    assert advised_severity("not a mapping") is None


def test_override_replaces_the_suggestion():
    assert advised_severity({"id": "X", "severity": "major"}, {"severity": "minor"}) == "minor"
    assert advised_severity({"id": "X", "severity": "major"}, {"severity": "nope"}) == "major"
    assert advised_severity({"id": "X"}, {"severity": "critical"}) == "critical"


def test_compact_renderer_carries_severity_and_override():
    plain = json.loads(render_compact_standards(COMPILED, "security"))
    first = plain[0]["requirements"][0]
    assert first["severity"] == "critical"
    overridden = json.loads(render_compact_standards(
        COMPILED, "security", overrides={first["id"]: {"severity": "minor"}}))
    assert overridden[0]["requirements"][0]["severity"] == "minor"


def test_compiled_and_grouped_renderers_carry_severity():
    md = render_compiled_standards(COMPILED, "security")
    assert "[suggested severity: critical]" in md
    grouped = json.loads(render_standards_grouped(json.load(open(COMPILED / "security.json"))))
    assert grouped[0]["requirements"][0]["severity"] == "critical"


def test_grouped_renderer_applies_the_override():
    data = json.load(open(COMPILED / "security.json"))
    req_id = data["principles"][0]["requirements"][0]["id"]
    grouped = json.loads(render_standards_grouped(data, overrides={req_id: {"severity": "minor"}}))
    assert grouped[0]["requirements"][0]["severity"] == "minor"


def test_rules_carry_the_suggestion_paragraph():
    assert "suggested severity" in load_evaluation_rules()
