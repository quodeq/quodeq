from quodeq.verifier.prompt import SYSTEM_PROMPT_V8, render_user_prompt


def test_system_prompt_names_all_four_questions():
    for q in ("Q1.", "Q2.", "Q3.", "Q4."):
        assert q in SYSTEM_PROMPT_V8, f"system prompt missing {q}"


def test_system_prompt_includes_concrete_worked_example():
    """Empirically v7.2 needed a concrete worked example; v8 keeps the
    pattern. Without it Gemma collapses to all-unknown."""
    assert "EXPECTED CHECKLIST ANSWER" in SYSTEM_PROMPT_V8
    # The example is RETRY_COUNT (a hardcoded numeric) so the model sees a
    # complete example response.
    assert "RETRY_COUNT" in SYSTEM_PROMPT_V8


def test_system_prompt_forbids_unanchored_citations():
    """Citation discipline is what keeps Gemma from inventing override seams."""
    assert "Never cite a line that is not visible" in SYSTEM_PROMPT_V8


def test_render_user_prompt_includes_finding_and_context():
    finding = {
        "file": "src/foo/bar.py",
        "line": 42,
        "title": "Hardcoded timeout",
        "reason": "The HTTP timeout is hardcoded as 30 seconds.",
        "snippet": "TIMEOUT = 30",
        "enclosing_role": "module",
    }
    context = "   40: import requests\n   41:\n>>> 42: TIMEOUT = 30\n   43:\n"
    out = render_user_prompt(finding, context)
    assert "Hardcoded timeout" in out
    assert "The HTTP timeout is hardcoded as 30 seconds." in out
    assert "src/foo/bar.py" in out
    assert "TIMEOUT = 30" in out
    assert ">>> 42:" in out


def test_render_user_prompt_marks_cited_line():
    """The rendered prompt's context block is the caller's responsibility,
    but render_user_prompt must include it verbatim under EVIDENCE."""
    finding = {
        "file": "f.py", "line": 1, "title": "t", "reason": "r",
        "snippet": "x", "enclosing_role": "module",
    }
    ctx_with_marker = ">>>  1: x"
    out = render_user_prompt(finding, ctx_with_marker)
    assert ctx_with_marker in out
