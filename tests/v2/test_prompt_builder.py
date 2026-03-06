"""Tests for v2 prompt builder."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from codecompass.v2.engine.prompt_builder import (
    build_analysis_prompt,
    load_template,
    render_practices,
    render_dimensions,
)


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
            },
            {
                "id": "ts-002",
                "title": "Keep functions small",
                "cwe": 1121,
                "dimension": "maintainability",
                "severity": "medium",
                "bad": "function f() { /* 100 lines */ }",
                "good": "function f() { doA(); doB(); }",
                "explanation": "Small functions are easier to test",
            },
        ],
    }


def _sample_dimensions():
    return {
        "applies": [
            {"id": "security", "weight": 1.2, "iso_25010": "Security", "source": "OWASP"},
            {"id": "maintainability", "weight": 1.0, "iso_25010": "Maintainability"},
        ],
        "excludes": ["usability"],
    }


# ---------------------------------------------------------------------------
# render_practices
# ---------------------------------------------------------------------------

class TestRenderPractices:
    def test_all_practices(self):
        text = render_practices(_sample_practices())
        assert "ts-001" in text
        assert "ts-002" in text
        assert "Avoid eval()" in text

    def test_filter_by_dimension(self):
        text = render_practices(_sample_practices(), dimension="security")
        assert "ts-001" in text
        assert "ts-002" not in text

    def test_empty_practices(self):
        text = render_practices({"practices": []}, dimension="security")
        assert "No practices" in text

    def test_includes_metadata(self):
        text = render_practices(_sample_practices(), dimension="security")
        assert "CWE" in text
        assert "95" in text
        assert "high" in text
        assert "eval is dangerous" in text


# ---------------------------------------------------------------------------
# render_dimensions
# ---------------------------------------------------------------------------

class TestRenderDimensions:
    def test_basic_rendering(self):
        text = render_dimensions(_sample_dimensions(), "security")
        assert "security" in text
        assert "1.2" in text
        assert "OWASP" in text

    def test_missing_dimension(self):
        text = render_dimensions(_sample_dimensions(), "nonexistent")
        assert "not configured" in text

    def test_with_standards(self, tmp_path):
        iso_dir = tmp_path / "iso25010"
        iso_dir.mkdir()
        std = {
            "sub_characteristics": [
                {
                    "name": "Confidentiality",
                    "requirements": [
                        {"id": "S-CON-1", "text": "Secrets MUST NOT be hardcoded"},
                    ],
                },
            ],
        }
        (iso_dir / "security.json").write_text(json.dumps(std))
        text = render_dimensions(_sample_dimensions(), "security", standards_dir=tmp_path)
        assert "Confidentiality" in text
        assert "S-CON-1" in text


# ---------------------------------------------------------------------------
# load_template
# ---------------------------------------------------------------------------

def test_load_template():
    template = load_template()
    assert "{{DISCIPLINE}}" in template
    assert "{{PRACTICES}}" in template
    assert "{{DIMENSION}}" in template


def test_load_template_custom_path(tmp_path):
    custom = tmp_path / "test.md"
    custom.write_text("Hello {{NAME}}")
    text = load_template(custom)
    assert text == "Hello {{NAME}}"


# ---------------------------------------------------------------------------
# build_analysis_prompt
# ---------------------------------------------------------------------------

class TestBuildAnalysisPrompt:
    def test_substitutes_all_variables(self):
        template = load_template()
        prompt = build_analysis_prompt(
            template,
            plugin_id="typescript",
            repo_name="my-app",
            date_str="2026-03-06",
            dimension="security",
            source_file_count=42,
            practices_data=_sample_practices(),
            dimensions_data=_sample_dimensions(),
        )
        assert "{{" not in prompt  # all placeholders resolved
        assert "my-app" in prompt
        assert "2026-03-06" in prompt
        assert "42" in prompt
        assert "ts-001" in prompt
        assert "security" in prompt

    def test_filters_practices_to_dimension(self):
        template = load_template()
        prompt = build_analysis_prompt(
            template,
            plugin_id="typescript",
            repo_name="test",
            date_str="2026-03-06",
            dimension="security",
            source_file_count=10,
            practices_data=_sample_practices(),
            dimensions_data=_sample_dimensions(),
        )
        assert "ts-001" in prompt  # security practice
        assert "ts-002" not in prompt  # maintainability practice filtered out

    def test_includes_analysis_guidance(self):
        template = load_template()
        prompt = build_analysis_prompt(
            template,
            plugin_id="typescript",
            repo_name="test",
            date_str="2026-03-06",
            dimension="security",
            source_file_count=10,
            practices_data=_sample_practices(),
            dimensions_data=_sample_dimensions(),
            analysis_md="Look for eval() calls in route handlers",
        )
        assert "Look for eval() calls in route handlers" in prompt

    def test_no_analysis_guidance_placeholder(self):
        template = load_template()
        prompt = build_analysis_prompt(
            template,
            plugin_id="typescript",
            repo_name="test",
            date_str="2026-03-06",
            dimension="security",
            source_file_count=10,
            practices_data=_sample_practices(),
            dimensions_data=_sample_dimensions(),
        )
        assert "No additional guidance" in prompt

    def test_prompt_hash_present(self):
        template = load_template()
        prompt = build_analysis_prompt(
            template,
            plugin_id="typescript",
            repo_name="test",
            date_str="2026-03-06",
            dimension="security",
            source_file_count=10,
            practices_data=_sample_practices(),
            dimensions_data=_sample_dimensions(),
        )
        # Hash is 12 hex chars
        assert "PROMPT_HASH" not in prompt
