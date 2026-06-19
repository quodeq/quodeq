"""The critical-severity bar must require reachable input provenance.

Run fa56db32 marked 4 of 6 'critical' findings as false positives: unguarded
prop/arg dereferences (R-FT-2) and a path-from-string (S-AUT-3) where the value
is provably internal (a hook default, a literal, a SHA-256 cache key). A finding
is only `critical` when a bad/attacker-controlled value can actually reach the
line. These tests guard the rubric text AND that it reaches the default
per-dimension producer path (compass.md), which historically dropped the rubric
because it had no {{EVALUATION_RULES}} placeholder.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis.prompts.builder import PromptContext, build_analysis_prompt
from quodeq.analysis.prompts._template import load_template

RULES = Path("src/quodeq/data/prompts/evaluation_rules.md").read_text()
COMPASS = Path("src/quodeq/data/prompts/compass.md").read_text()


def test_rules_define_provenance_selfcheck():
    """The self-check must add a provenance gate beyond the test-file carve-out."""
    lower = RULES.lower()
    assert "provenance" in lower
    assert "attacker-controlled" in lower
    # The gate must name the escape hatch for provably-internal values.
    assert "hardening gap" in lower


def test_rules_show_internal_input_examples():
    """Concrete internal-input examples anchor the gate for weaker local models."""
    lower = RULES.lower()
    # A content hash / SHA-256 key is the canonical non-attacker-controlled path.
    assert "content hash" in lower or "sha-256" in lower
    # A defaulted prop/arg is the canonical unguarded-access false positive.
    assert "default" in lower


def test_rules_keep_external_input_critical():
    """The contrast example must keep genuinely external provenance critical."""
    lower = RULES.lower()
    # An HTTP request / query string is the canonical attacker-controlled source.
    assert "request" in lower


def test_compass_injects_evaluation_rules():
    """compass.md (default per-dimension template) must carry the rubric slot.

    Without the placeholder the rubric value is computed in builder.py and
    silently dropped, so the default path scores severity with no guidance.
    """
    assert "{{EVALUATION_RULES}}" in COMPASS


def test_compass_prompt_renders_provenance_gate_end_to_end():
    """Building the default template must land the provenance gate in the output."""
    template = load_template()  # defaults to compass.md
    ctx = PromptContext(
        language="python",
        repo_name="test-repo",
        date_str="2026-06-19",
        dimension="security",
        source_file_count=50,
        dimensions_data={"applies": [{"id": "security"}], "excludes": []},
    )
    result = build_analysis_prompt(template, ctx).lower()
    assert "provenance" in result
    assert "attacker-controlled" in result
