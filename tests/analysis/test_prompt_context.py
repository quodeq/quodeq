from quodeq.analysis.prompts._context import PromptContext


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
