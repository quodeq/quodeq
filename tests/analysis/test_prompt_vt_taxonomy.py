"""The CLI prompts must offer the optional 'vt' taxonomy parameter.

Without the prompt instruction no MCP-path producer ever emits a taxonomy,
so fresh runs score with taxonomy_used=False (free-text reason grouping).
"""
from __future__ import annotations

from pathlib import Path

SUBAGENT = Path("src/quodeq/data/prompts/cli_subagent_prompt.md").read_text()
CONSOLIDATED = Path("src/quodeq/data/prompts/cli_consolidated_prompt.md").read_text()
COMPASS = Path("src/quodeq/data/prompts/compass.md").read_text()


def _optional_params_line(prompt: str) -> str:
    return next(line for line in prompt.splitlines() if line.startswith("**Optional:**"))


def _vt_field_line(prompt: str) -> str:
    return next(line for line in prompt.splitlines() if line.startswith("- `vt`"))


def test_subagent_prompt_offers_vt_param():
    assert "`vt`" in _optional_params_line(SUBAGENT)


def test_consolidated_prompt_offers_vt_param():
    assert "`vt`" in _optional_params_line(CONSOLIDATED)


def test_compass_prompt_offers_vt_param():
    # compass.md is the default per-dimension analysis template, the
    # most-exercised MCP/CLI producer path. Its report_finding field list
    # must offer 'vt' too, or the default path never emits a taxonomy.
    line = _vt_field_line(COMPASS)
    assert "`vt`" in line


def test_prompts_explain_stable_taxonomy_codes():
    for prompt in (SUBAGENT, CONSOLIDATED):
        line = _optional_params_line(prompt)
        assert "taxonomy" in line.lower()
        assert "code-injection" in line  # concrete example anchors the format
    compass_line = _vt_field_line(COMPASS)
    assert "taxonomy" in compass_line.lower()
    assert "code-injection" in compass_line
