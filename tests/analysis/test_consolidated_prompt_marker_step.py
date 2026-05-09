from __future__ import annotations
from pathlib import Path


PROMPT = Path("src/quodeq/data/prompts/cli_consolidated_prompt.md").read_text()


def test_workflow_mentions_mark_file_done():
    # The prompt instructs the agent to call mark_file_done after each file.
    assert "mark_file_done" in PROMPT


def test_workflow_step_is_in_workflow_section():
    workflow_idx = PROMPT.index("## Workflow")
    next_section_idx = PROMPT.index("\n## ", workflow_idx + 1)
    workflow_section = PROMPT[workflow_idx:next_section_idx]
    assert "mark_file_done" in workflow_section


def test_status_values_documented():
    assert "status='ok'" in PROMPT or 'status="ok"' in PROMPT
    assert "status='error'" in PROMPT or 'status="error"' in PROMPT
