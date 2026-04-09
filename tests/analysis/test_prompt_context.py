from quodeq.analysis.prompts._context import PromptContext
from quodeq.analysis.prompts.builder import render_previous_findings_section


def test_prompt_context_default_previous_findings():
    ctx = PromptContext(
        language="python", repo_name="test", date_str="2026-01-01",
        dimension="security", source_file_count=10, dimensions_data={},
    )
    assert ctx.previous_findings == []


def test_prompt_context_with_previous_findings():
    findings = [
        {"p": "Security", "t": "violation", "file": "a.py", "line": 1, "reason": "test"},
    ]
    ctx = PromptContext(
        language="python", repo_name="test", date_str="2026-01-01",
        dimension="security", source_file_count=10, dimensions_data={},
        previous_findings=findings,
    )
    assert ctx.previous_findings == findings


def test_render_previous_findings_empty():
    assert render_previous_findings_section([]) == ""


def test_render_previous_findings_groups_by_file():
    findings = [
        {"p": "Security", "t": "violation", "file": "a.py", "line": 42, "req": "S-CON-3", "reason": "hardcoded creds"},
        {"p": "Security", "t": "compliance", "file": "a.py", "line": 55, "req": "S-CON-5", "reason": "good validation"},
        {"p": "Maintainability", "t": "violation", "file": "b.py", "line": 100, "req": "P-MOD-1", "reason": "long function"},
    ]
    result = render_previous_findings_section(findings)
    assert "### a.py" in result
    assert "### b.py" in result
    assert "[violation] S-CON-3" in result
    assert "[compliance] S-CON-5" in result
    assert "[violation] P-MOD-1" in result
    assert "hardcoded creds" in result
    assert "Previous findings" in result


def test_render_previous_findings_no_file_key():
    findings = [{"p": "X", "t": "violation", "reason": "no file"}]
    result = render_previous_findings_section(findings)
    assert "### (unknown file)" in result
