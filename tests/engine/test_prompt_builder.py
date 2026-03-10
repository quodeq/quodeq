"""Tests for prompt builder."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.engine.prompt_builder import (
    PromptContext,
    build_analysis_prompt,
    load_template,
    render_compiled_standards,
    render_dimensions,
)


def _sample_dimensions():
    return {
        "applies": [
            {"id": "security", "weight": 1.2, "iso_25010": "Security", "source": "OWASP"},
            {"id": "maintainability", "weight": 1.0, "iso_25010": "Maintainability"},
        ],
        "excludes": ["usability"],
    }


# ---------------------------------------------------------------------------
# render_compiled_standards
# ---------------------------------------------------------------------------

class TestRenderCompiledStandards:
    def test_renders_principles_and_requirements(self, tmp_path):
        compiled = {
            "id": "reliability",
            "principles": [
                {
                    "name": "Fault Tolerance",
                    "source": "iso25010",
                    "requirements": [
                        {"id": "R-FT-1", "source": "iso25010",
                         "text": "Exceptions MUST be caught and handled", "refs": []},
                        {"id": "R-FT-2", "source": "iso25010",
                         "text": "Null dereferences MUST be guarded", "refs": []},
                    ],
                },
                {
                    "name": "Maturity",
                    "source": "iso25010",
                    "requirements": [
                        {"id": "R-MAT-1", "source": "iso25010",
                         "text": "All public functions MUST have tests", "refs": []},
                    ],
                },
            ],
        }
        (tmp_path / "reliability.json").write_text(json.dumps(compiled))
        text = render_compiled_standards(tmp_path, "reliability")
        assert "### Fault Tolerance" in text
        assert "**R-FT-1**" in text
        assert "Exceptions MUST be caught and handled" in text
        assert "**R-FT-2**" in text
        assert "### Maturity" in text
        assert "**R-MAT-1**" in text
        assert "CWE-" not in text

    def test_missing_dimension(self, tmp_path):
        text = render_compiled_standards(tmp_path, "nonexistent")
        assert "No compiled standards" in text

    def test_empty_requirements(self, tmp_path):
        compiled = {"id": "test", "principles": [{"name": "Empty", "source": "iso25010", "requirements": []}]}
        (tmp_path / "test.json").write_text(json.dumps(compiled))
        text = render_compiled_standards(tmp_path, "test")
        assert "Empty" not in text


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

    def test_renders_weight_and_iso(self):
        text = render_dimensions(_sample_dimensions(), "security")
        assert "**Weight:** 1.2" in text
        assert "**ISO 25010:** Security" in text


# ---------------------------------------------------------------------------
# load_template
# ---------------------------------------------------------------------------

def test_load_template():
    template = load_template()
    assert "{{DISCIPLINE}}" in template
    assert "{{STANDARDS_CHECKLIST}}" in template
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
    def test_substitutes_all_variables(self, tmp_path):
        # Create minimal compiled standards
        compiled_dir = tmp_path / "compiled"
        compiled_dir.mkdir()
        compiled = {
            "id": "security",
            "principles": [
                {
                    "name": "Confidentiality",
                    "source": "iso25010",
                    "requirements": [
                        {"id": "S-CON-1", "source": "iso25010",
                         "text": "Secrets MUST NOT be hardcoded in source", "refs": []}
                    ],
                },
            ],
        }
        (compiled_dir / "security.json").write_text(json.dumps(compiled))

        template = load_template()
        prompt = build_analysis_prompt(
            template,
            PromptContext(
                plugin_id="typescript",
                repo_name="my-app",
                date_str="2026-03-06",
                dimension="security",
                source_file_count=42,
                dimensions_data=_sample_dimensions(),
                standards_dir=tmp_path,
            ),
        )
        assert "{{" not in prompt  # all placeholders resolved
        assert "my-app" in prompt
        assert "2026-03-06" in prompt
        assert "42" in prompt
        assert "Confidentiality" in prompt
        assert "S-CON-1" in prompt
        assert "Secrets MUST NOT be hardcoded" in prompt
        assert "security" in prompt

    def test_includes_analysis_guidance(self):
        template = load_template()
        prompt = build_analysis_prompt(
            template,
            PromptContext(
                plugin_id="typescript",
                repo_name="test",
                date_str="2026-03-06",
                dimension="security",
                source_file_count=10,
                dimensions_data=_sample_dimensions(),
                analysis_md="Look for eval() calls in route handlers",
            ),
        )
        assert "Look for eval() calls in route handlers" in prompt

    def test_no_analysis_guidance_placeholder(self):
        template = load_template()
        prompt = build_analysis_prompt(
            template,
            PromptContext(
                plugin_id="typescript",
                repo_name="test",
                date_str="2026-03-06",
                dimension="security",
                source_file_count=10,
                dimensions_data=_sample_dimensions(),
            ),
        )
        assert "No additional guidance" in prompt

    def test_prompt_hash_present(self):
        template = load_template()
        prompt = build_analysis_prompt(
            template,
            PromptContext(
                plugin_id="typescript",
                repo_name="test",
                date_str="2026-03-06",
                dimension="security",
                source_file_count=10,
                dimensions_data=_sample_dimensions(),
            ),
        )
        assert "PROMPT_HASH" not in prompt
