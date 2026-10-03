"""load_standards_text cuts both the JSON and the Markdown source at the budget."""
from __future__ import annotations

import json

from quodeq.analysis.subprocess import load_standards_text

MARKER = "\n\n[... standards truncated for context limits ...]"


def test_markdown_over_budget_is_cut_at_the_budget_and_marked(tmp_path):
    (tmp_path / "security.md").write_text("abcdefghij")
    assert load_standards_text(tmp_path, "security", max_chars=4) == "abcd" + MARKER


def test_markdown_within_budget_is_returned_unchanged(tmp_path):
    (tmp_path / "security.md").write_text("abcd")
    assert load_standards_text(tmp_path, "security", max_chars=4) == "abcd"


def test_json_over_budget_is_cut_at_the_budget_and_marked(tmp_path):
    data = {"principles": [{"name": "P", "requirements": [{"id": "R-1", "text": "x" * 200}]}]}
    (tmp_path / "security.json").write_text(json.dumps(data))
    full = load_standards_text(tmp_path, "security", max_chars=100_000)
    assert load_standards_text(tmp_path, "security", max_chars=10) == full[:10] + MARKER
