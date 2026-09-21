"""Extended tests for prompts/builder.py — prompt assembly, previous findings."""
from __future__ import annotations

import json
from unittest.mock import patch


from quodeq.analysis.prompts.builder import (
    PromptContext,
    build_analysis_prompt,
    build_consolidated_prompt,
    render_previous_findings_section,
    load_evaluation_rules,
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
# load_evaluation_rules
# ---------------------------------------------------------------------------

class TestLoadEvaluationRules:
    def test_returns_string(self):
        result = load_evaluation_rules()
        assert isinstance(result, str)

    def test_returns_empty_on_missing_file(self):
        with patch("quodeq.analysis.prompts.builder.load_template", side_effect=FileNotFoundError):
            result = load_evaluation_rules()
        assert result == ""


# Every placeholder the two prompt shapes fill. A template that omits one
# would leave a literal "{{...}}" in the rendered prompt, so each test spells
# out the full set; building it from these keeps the eight templates below
# from drifting apart.
_COMMON_SLOTS = (
    "DISCIPLINE", "REPO_NAME", "DATE", "SOURCE_FILE_COUNT",
    "ANALYSIS_GUIDANCE", "PROMPT_HASH", "SOURCE_MANIFEST", "EVALUATION_RULES",
)
_ANALYSIS_SLOTS = (*_COMMON_SLOTS, "DIMENSION", "STANDARDS_CHECKLIST", "DIMENSIONS")
_CONSOLIDATED_SLOTS = (*_COMMON_SLOTS, "DIMENSION_LIST", "STANDARDS_CHECKLISTS")


def _template(slots: tuple[str, ...], prefix: str = "") -> str:
    """A template filling every slot in *slots*, after an optional *prefix*."""
    return prefix + " ".join(f"{{{{{slot}}}}}" for slot in slots)


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
        template = _template(_ANALYSIS_SLOTS, "Analyze ")
        ctx = self._make_context()
        result = build_analysis_prompt(template, ctx)
        assert "python" in result
        assert "test-repo" in result
        assert "2026-04-09" in result
        assert "security" in result

    def test_includes_previous_findings(self):
        template = _template(_ANALYSIS_SLOTS, "Test ")
        findings = [{"file": "a.py", "t": "violation", "req": "S-1", "line": 5, "reason": "Bad"}]
        ctx = self._make_context(previous_findings=findings)
        result = build_analysis_prompt(template, ctx)
        assert "Previous findings" in result
        assert "a.py" in result

    def test_no_standards_without_dir(self):
        template = _template(_ANALYSIS_SLOTS, "Standards: ")
        ctx = self._make_context(standards_dir=None)
        result = build_analysis_prompt(template, ctx)
        assert "No compiled standards" in result

    def test_extra_vars_substituted(self):
        template = _template(_ANALYSIS_SLOTS, "Custom: {{MY_VAR}} ")
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

        template = _template(_ANALYSIS_SLOTS, "Standards: ")
        ctx = self._make_context(standards_dir=standards_dir)
        result = build_analysis_prompt(template, ctx)
        # Must render the compiled principle, not fall back to the sentinel.
        assert "No compiled standards" not in result
        assert "Auth" in result


# ---------------------------------------------------------------------------
# build_consolidated_prompt
# ---------------------------------------------------------------------------

class TestBuildConsolidatedPrompt:
    @staticmethod
    def _make_context(**kwargs) -> PromptContext:
        defaults = dict(
            language="python",
            repo_name="test",
            date_str="2026-04-09",
            dimension="consolidated",
            source_file_count=10,
            dimensions_data={},
        )
        defaults.update(kwargs)
        return PromptContext(**defaults)

    def test_basic_rendering(self):
        template = _template(_CONSOLIDATED_SLOTS, "Dimensions: ")
        ctx = self._make_context(
            language="typescript", repo_name="my-app", source_file_count=100,
        )
        result = build_consolidated_prompt(["security", "reliability"], ctx, template=template)
        assert "security, reliability" in result
        assert "typescript" in result

    def test_no_standards_without_dir(self):
        template = _template(_CONSOLIDATED_SLOTS, "Standards: ")
        ctx = self._make_context(standards_dir=None)
        result = build_consolidated_prompt(["security"], ctx, template=template)
        assert "No compiled standards" in result

    def test_extra_vars(self):
        template = _template(_CONSOLIDATED_SLOTS, "Custom: {{MY_VAR}} ")
        ctx = self._make_context(extra_vars={"MY_VAR": "world"})
        result = build_consolidated_prompt(["security"], ctx, template=template)
        assert "world" in result

    def test_loads_default_template_when_none(self):
        ctx = self._make_context()
        # Should not raise — loads template from disk
        result = build_consolidated_prompt(["security"], ctx)
        assert isinstance(result, str)
        assert len(result) > 0
