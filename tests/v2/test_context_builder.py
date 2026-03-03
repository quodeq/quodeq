from __future__ import annotations

import json
from pathlib import Path

from codecompass.v2.engine.context_builder import build_judge_context
from codecompass.v2.engine.finding import Finding


def _sample_finding(**overrides) -> Finding:
    defaults = {
        "rule": "cwe_95_eval",
        "label": "CWE-95: eval()",
        "file": "src/app.ts",
        "dimension": "security",
        "detector": "grep",
        "cwe": 95,
        "line": 10,
        "snippet": "eval(userInput)",
    }
    defaults.update(overrides)
    return Finding(**defaults)


def _sample_practices() -> dict:
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


def _sample_dimensions() -> dict:
    return {
        "applies": [
            {"id": "security", "weight": 1.2, "iso_25010": "Security", "source": "OWASP"},
            {"id": "maintainability", "weight": 1.0},
        ],
    }


def test_empty_findings():
    ctx = build_judge_context([], {}, "", {"applies": []})
    assert "No findings" in ctx


def test_findings_grouped_by_dimension():
    findings = [
        _sample_finding(dimension="security"),
        _sample_finding(dimension="maintainability", rule="cwe_1080", label="Large file", cwe=1080),
    ]
    ctx = build_judge_context(findings, {}, "", {"applies": []})
    assert "### Security" in ctx
    assert "### Maintainability" in ctx


def test_practices_formatting():
    ctx = build_judge_context([], _sample_practices(), "", {"applies": []})
    assert "ts-001" in ctx
    assert "Avoid eval()" in ctx
    assert "eval is dangerous" in ctx


def test_full_context_has_all_sections():
    findings = [_sample_finding()]
    ctx = build_judge_context(
        findings,
        _sample_practices(),
        "Look for eval() calls",
        _sample_dimensions(),
    )
    assert "## Detector Findings" in ctx
    assert "## Practices" in ctx
    assert "## Analysis Guidance" in ctx
    assert "## Dimensions" in ctx


def test_code_snippet_extraction(tmp_path):
    src_file = tmp_path / "app.ts"
    src_file.write_text("line1\nline2\nline3\neval(x)\nline5\nline6\n")
    finding = _sample_finding(file=str(src_file), line=4)
    ctx = build_judge_context([finding], {}, "", {"applies": []}, src_dir=tmp_path)
    assert "Code Context" in ctx
    assert "eval(x)" in ctx


def test_grouped_sub_characteristics_in_output(tmp_path):
    """Test that the new grouped sub_characteristics structure renders correctly."""
    std_dir = tmp_path / "standards"
    iso_dir = std_dir / "iso25010"
    iso_dir.mkdir(parents=True)

    # Write a standards file with the new grouped structure
    std_data = {
        "id": "security",
        "name": "Security",
        "iso_25010": "Security",
        "version": "2023",
        "sub_characteristics": [
            {
                "name": "Confidentiality",
                "requirements": [
                    {"id": "S-CON-1", "text": "Secrets MUST NOT be hardcoded", "cwe": [798]},
                    {"id": "S-CON-2", "text": "Sensitive data MUST NOT be logged", "cwe": [532]},
                ],
            },
            {
                "name": "Integrity",
                "requirements": [
                    {"id": "S-INT-1", "text": "All input MUST be validated", "cwe": [20]},
                ],
            },
        ],
    }
    (iso_dir / "security.json").write_text(json.dumps(std_data))

    dims = {"applies": [{"id": "security", "weight": 1.2, "iso_25010": "Security"}]}
    ctx = build_judge_context([], {}, "", dims, standards_dir=std_dir)

    # Sub-characteristic names should appear
    assert "Confidentiality" in ctx
    assert "Integrity" in ctx
    # Requirement IDs and text should appear
    assert "S-CON-1" in ctx
    assert "Secrets MUST NOT be hardcoded" in ctx
    assert "S-INT-1" in ctx


def test_legacy_flat_requirements_backward_compat(tmp_path):
    """Test backward compatibility with legacy flat requirements array."""
    std_dir = tmp_path / "standards"
    iso_dir = std_dir / "iso25010"
    iso_dir.mkdir(parents=True)

    # Write a legacy-format standards file
    std_data = {
        "id": "security",
        "name": "Security",
        "sub_characteristics": ["Confidentiality", "Integrity"],
        "requirements": [
            {"id": "S-1", "text": "No eval with user input", "cwe": [95]},
        ],
    }
    (iso_dir / "security.json").write_text(json.dumps(std_data))

    dims = {"applies": [{"id": "security", "weight": 1.0}]}
    ctx = build_judge_context([], {}, "", dims, standards_dir=std_dir)

    assert "S-1" in ctx
    assert "No eval with user input" in ctx
