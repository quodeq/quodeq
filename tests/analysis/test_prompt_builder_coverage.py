"""Extended tests for prompts/builder.py — prompt assembly, previous findings."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis.prompts.builder import (
    PromptContext,
    build_analysis_prompt,
    build_consolidated_prompt,
    render_previous_findings_section,
    _load_evaluation_rules,
)


# ---------------------------------------------------------------------------
# render_previous_findings_section
# ---------------------------------------------------------------------------

class TestRenderPreviousFindings:
    def test_empty_findings_returns_empty(self):
        assert render_previous_findings_section([]) == ""

    def test_renders_findings_grouped_by_file(self):
        findings = [
            {"file": "a.py", "t": "violation", "req": "S-1", "line": 10, "reason": "Bad input"},
            {"file": "a.py", "t": "compliance", "req": "S-2", "line": 20, "reason": "Good auth"},
            {"file": "b.py", "t": "violation", "req": "M-1", "line": 5, "reason": "Complex"},
        ]
        result = render_previous_findings_section(findings)
        assert "### a.py" in result
        assert "### b.py" in result
        assert "[violation] S-1 line 10: Bad input" in result
        assert "[compliance] S-2 line 20: Good auth" in result
        assert "[violation] M-1 line 5: Complex" in result

    def test_handles_missing_fields(self):
        findings = [{"file": "x.py"}]
        result = render_previous_findings_section(findings)
        assert "### x.py" in result
        assert "[finding]" in result

    def test_groups_unknown_file(self):
        findings = [{"t": "violation", "req": "X-1"}]
        result = render_previous_findings_section(findings)
        assert "(unknown file)" in result

    def test_includes_instruction_text(self):
        findings = [{"file": "a.py", "t": "violation", "req": "X-1", "line": 1}]
        result = render_previous_findings_section(findings)
        assert "Previous findings" in result
        assert "confirm whether these findings still apply" in result


# ---------------------------------------------------------------------------
# _load_evaluation_rules
# ---------------------------------------------------------------------------

class TestLoadEvaluationRules:
    def test_returns_string(self):
        result = _load_evaluation_rules()
        assert isinstance(result, str)

    def test_returns_empty_on_missing_file(self):
        with patch("quodeq.analysis.prompts.builder.load_template", side_effect=FileNotFoundError):
            result = _load_evaluation_rules()
        assert result == ""


# ---------------------------------------------------------------------------
# build_analysis_prompt
# ---------------------------------------------------------------------------

class TestBuildAnalysisPrompt:
    def _make_context(self, tmp_path=None, **kwargs):
        defaults = dict(
            language="python",
            repo_name="test-repo",
            date_str="2026-04-09",
            dimension="security",
            source_file_count=50,
            dimensions_data={"applies": [{"id": "security"}], "excludes": []},
        )
        defaults.update(kwargs)
        return PromptContext(**defaults)

    def test_basic_prompt_rendering(self):
        template = "Analyze {{DISCIPLINE}} project {{REPO_NAME}} on {{DATE}} for {{DIMENSION}}. Files: {{SOURCE_FILE_COUNT}}. Standards: {{STANDARDS_CHECKLIST}}. Guidance: {{ANALYSIS_GUIDANCE}}. Dims: {{DIMENSIONS}}. Hash: {{PROMPT_HASH}}. Manifest: {{SOURCE_MANIFEST}}. Rules: {{EVALUATION_RULES}}."
        ctx = self._make_context()
        result = build_analysis_prompt(template, ctx)
        assert "python" in result
        assert "test-repo" in result
        assert "2026-04-09" in result
        assert "security" in result

    def test_includes_previous_findings(self):
        template = "Test {{DISCIPLINE}} {{REPO_NAME}} {{DATE}} {{DIMENSION}} {{SOURCE_FILE_COUNT}} {{STANDARDS_CHECKLIST}} {{ANALYSIS_GUIDANCE}} {{DIMENSIONS}} {{PROMPT_HASH}} {{SOURCE_MANIFEST}} {{EVALUATION_RULES}}"
        findings = [{"file": "a.py", "t": "violation", "req": "S-1", "line": 5, "reason": "Bad"}]
        ctx = self._make_context(previous_findings=findings)
        result = build_analysis_prompt(template, ctx)
        assert "Previous findings" in result
        assert "a.py" in result

    def test_no_standards_without_dir(self):
        template = "Standards: {{STANDARDS_CHECKLIST}} {{DISCIPLINE}} {{REPO_NAME}} {{DATE}} {{DIMENSION}} {{SOURCE_FILE_COUNT}} {{ANALYSIS_GUIDANCE}} {{DIMENSIONS}} {{PROMPT_HASH}} {{SOURCE_MANIFEST}} {{EVALUATION_RULES}}"
        ctx = self._make_context(standards_dir=None)
        result = build_analysis_prompt(template, ctx)
        assert "No compiled standards" in result

    def test_extra_vars_substituted(self):
        template = "Custom: {{MY_VAR}} {{DISCIPLINE}} {{REPO_NAME}} {{DATE}} {{DIMENSION}} {{SOURCE_FILE_COUNT}} {{STANDARDS_CHECKLIST}} {{ANALYSIS_GUIDANCE}} {{DIMENSIONS}} {{PROMPT_HASH}} {{SOURCE_MANIFEST}} {{EVALUATION_RULES}}"
        ctx = self._make_context(extra_vars={"MY_VAR": "hello"})
        result = build_analysis_prompt(template, ctx)
        assert "hello" in result

    def test_compiled_standards_loaded(self, tmp_path):
        standards_dir = tmp_path / "standards"
        standards_dir.mkdir()
        compiled = standards_dir / "compiled"
        compiled.mkdir()
        compiled.joinpath("security.json").write_text(json.dumps({
            "id": "security",
            "principles": [{"name": "Auth", "requirements": [{"id": "S-1", "text": "Use tokens"}]}],
        }))

        template = "Standards: {{STANDARDS_CHECKLIST}} {{DISCIPLINE}} {{REPO_NAME}} {{DATE}} {{DIMENSION}} {{SOURCE_FILE_COUNT}} {{ANALYSIS_GUIDANCE}} {{DIMENSIONS}} {{PROMPT_HASH}} {{SOURCE_MANIFEST}} {{EVALUATION_RULES}}"
        ctx = self._make_context(standards_dir=standards_dir)
        result = build_analysis_prompt(template, ctx)
        # Should contain standards content (not the "no standards" sentinel)
        assert "No compiled standards" not in result or "Auth" in result


# ---------------------------------------------------------------------------
# build_consolidated_prompt
# ---------------------------------------------------------------------------

class TestBuildConsolidatedPrompt:
    def test_basic_rendering(self):
        template = "Dimensions: {{DIMENSION_LIST}}. Standards: {{STANDARDS_CHECKLISTS}}. {{DISCIPLINE}} {{REPO_NAME}} {{DATE}} {{SOURCE_FILE_COUNT}} {{ANALYSIS_GUIDANCE}} {{PROMPT_HASH}} {{SOURCE_MANIFEST}} {{EVALUATION_RULES}}"
        ctx = PromptContext(
            language="typescript",
            repo_name="my-app",
            date_str="2026-04-09",
            dimension="consolidated",
            source_file_count=100,
            dimensions_data={},
        )
        result = build_consolidated_prompt(["security", "reliability"], ctx, template=template)
        assert "security, reliability" in result
        assert "typescript" in result

    def test_no_standards_without_dir(self):
        template = "Standards: {{STANDARDS_CHECKLISTS}} {{DISCIPLINE}} {{REPO_NAME}} {{DATE}} {{DIMENSION_LIST}} {{SOURCE_FILE_COUNT}} {{ANALYSIS_GUIDANCE}} {{PROMPT_HASH}} {{SOURCE_MANIFEST}} {{EVALUATION_RULES}}"
        ctx = PromptContext(
            language="python",
            repo_name="test",
            date_str="2026-04-09",
            dimension="consolidated",
            source_file_count=10,
            dimensions_data={},
            standards_dir=None,
        )
        result = build_consolidated_prompt(["security"], ctx, template=template)
        assert "No compiled standards" in result

    def test_extra_vars(self):
        template = "Custom: {{MY_VAR}} {{DISCIPLINE}} {{REPO_NAME}} {{DATE}} {{DIMENSION_LIST}} {{SOURCE_FILE_COUNT}} {{STANDARDS_CHECKLISTS}} {{ANALYSIS_GUIDANCE}} {{PROMPT_HASH}} {{SOURCE_MANIFEST}} {{EVALUATION_RULES}}"
        ctx = PromptContext(
            language="python",
            repo_name="test",
            date_str="2026-04-09",
            dimension="consolidated",
            source_file_count=10,
            dimensions_data={},
            extra_vars={"MY_VAR": "world"},
        )
        result = build_consolidated_prompt(["security"], ctx, template=template)
        assert "world" in result

    def test_loads_default_template_when_none(self):
        ctx = PromptContext(
            language="python",
            repo_name="test",
            date_str="2026-04-09",
            dimension="consolidated",
            source_file_count=10,
            dimensions_data={},
        )
        # Should not raise — loads template from disk
        result = build_consolidated_prompt(["security"], ctx)
        assert isinstance(result, str)
        assert len(result) > 0
