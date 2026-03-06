from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="detector/judge code removed in PR2")

import json

import pytest

from codecompass.v2.engine.judge import _parse_judge_output, _assemble_evidence, run_judge
from codecompass.v2.engine.evidence import Judgment


def _sample_practices():
    return {
        "runtime": "typescript",
        "version": "1.0.0",
        "practices": [
            {
                "id": "ts-001",
                "title": "Avoid eval()",
                "cwe": 95,
                "dimension": "security",
                "severity": "high",
                "bad": "eval(x)",
                "good": "JSON.parse(x)",
                "explanation": "eval is dangerous",
            }
        ],
    }


# ── JSONL parsing ────────────────────────────────────────────────────

def test_parse_valid_jsonl():
    raw = json.dumps({"practice_id": "ts-001", "verdict": "violation", "file": "a.ts", "line": 1, "severity": "high"})
    judgments, dismissed = _parse_judge_output(raw)
    assert len(judgments) == 1
    assert judgments[0].practice_id == "ts-001"
    assert judgments[0].verdict == "violation"
    assert dismissed == 0


def test_parse_with_markdown_fences():
    raw = "```json\n" + json.dumps({"practice_id": "ts-001", "verdict": "violation"}) + "\n```"
    judgments, dismissed = _parse_judge_output(raw)
    assert len(judgments) == 1


def test_parse_invalid_lines_skipped():
    raw = "not json\n" + json.dumps({"practice_id": "ts-001", "verdict": "violation"}) + "\nalso not json"
    judgments, _ = _parse_judge_output(raw)
    assert len(judgments) == 1


def test_parse_missing_required_fields():
    raw = json.dumps({"practice_id": "ts-001"})  # no verdict
    judgments, _ = _parse_judge_output(raw)
    assert len(judgments) == 0


def test_parse_dismissed_verdict():
    raw = json.dumps({"practice_id": "ts-001", "verdict": "dismissed"})
    judgments, dismissed = _parse_judge_output(raw)
    assert len(judgments) == 0
    assert dismissed == 1


def test_parse_compliance_verdict():
    raw = json.dumps({"practice_id": "ts-001", "verdict": "compliance", "file": "b.ts"})
    judgments, _ = _parse_judge_output(raw)
    assert len(judgments) == 1
    assert judgments[0].verdict == "compliance"


# ── Evidence assembly ────────────────────────────────────────────────

def test_assemble_evidence_groups_by_practice():
    judgments = [
        Judgment(practice_id="ts-001", verdict="violation", file="a.ts", line=1, severity="high", dimension="security"),
        Judgment(practice_id="ts-001", verdict="compliance", file="b.ts", line=2, dimension="security"),
        Judgment(practice_id="ts-002", verdict="violation", file="c.ts", line=3, severity="medium", dimension="maintainability"),
    ]
    practices = {
        "practices": [
            {"id": "ts-001", "title": "Avoid eval()", "dimension": "security", "severity": "high"},
            {"id": "ts-002", "title": "Small functions", "dimension": "maintainability", "severity": "medium"},
        ]
    }
    ev = _assemble_evidence(
        judgments=judgments,
        dismissed_count=1,
        repository="test",
        plugin_id="typescript",
        date_str="2026-03-03",
        practices=practices,
        source_file_count=10,
        files_read=5,
        coverage_pct=50.0,
    )
    assert "ts-001" in ev.principles
    assert "ts-002" in ev.principles
    assert len(ev.principles["ts-001"].violations) == 1
    assert len(ev.principles["ts-001"].compliance) == 1
    assert ev.dismissed_count == 1


# ── Mock AI caller ───────────────────────────────────────────────────

def test_run_judge_with_mock_ai():
    mock_output = "\n".join([
        json.dumps({"practice_id": "ts-001", "verdict": "violation", "file": "a.ts", "line": 1, "severity": "high", "reason": "eval", "dimension": "security"}),
        json.dumps({"practice_id": "ts-001", "verdict": "compliance", "file": "b.ts", "line": 5, "reason": "safe parse", "dimension": "security"}),
    ])

    def mock_ai(prompt):
        return (mock_output, None)

    ev = run_judge(
        context="test context",
        repository="test-repo",
        plugin_id="typescript",
        date_str="2026-03-03",
        practices=_sample_practices(),
        source_file_count=10,
        files_read=5,
        ai_caller=mock_ai,
    )
    assert ev.repository == "test-repo"
    assert "ts-001" in ev.principles
    assert ev.principles["ts-001"].metrics["is_balanced"] is True


def test_run_judge_ai_error():
    def mock_ai(prompt):
        return ("", "API error")

    with pytest.raises(RuntimeError, match="Judge AI call failed"):
        run_judge(
            context="test",
            repository="test",
            plugin_id="ts",
            date_str="",
            practices={},
            source_file_count=0,
            ai_caller=mock_ai,
        )
