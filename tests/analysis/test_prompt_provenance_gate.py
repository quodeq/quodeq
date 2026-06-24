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

import pytest

from quodeq.analysis.api_prompt_assembly import assemble_api_prompt
from quodeq.analysis.prompts.builder import PromptContext, build_analysis_prompt
from quodeq.analysis.prompts._template import load_template
from quodeq.context.path_role import Role, path_role
from tests.analysis._provenance_gate_support import discover_cases

RULES = Path("src/quodeq/data/prompts/evaluation_rules.md").read_text()
COMPASS = Path("src/quodeq/data/prompts/compass.md").read_text()

_CASES = discover_cases()
_CASE_IDS = [c.name for c in _CASES]


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


def test_api_prompt_renders_provenance_gate_end_to_end(tmp_path):
    """The DIRECT-API path (assemble_api_prompt) must also carry the gate.

    The existing tests only prove the compass.md producer path carries the
    rubric. ``assemble_api_prompt`` is the prompt the ollama/api provider path
    actually sends (``subprocess.py:_run_api_analysis_bridge``); it loads the
    rules itself via ``_load_evaluation_rules``, a separate seam that could
    regress independently. This is the structural backstop for the live
    behavioral matrix.
    """
    src = tmp_path / "sample.py"
    src.write_text("def f(x):\n    return open(x)\n", encoding="utf-8")
    prompt = assemble_api_prompt(
        source_files=[src],
        standards_text="",
        dimension="security",
        repo_name="sample",
        repo_root=tmp_path,
    ).lower()
    assert "provenance" in prompt
    assert "attacker-controlled" in prompt


def test_fixture_matrix_is_well_formed():
    """Guardrail: a misconfigured fixtures dir must fail loudly, not pass zero cases.

    Mirrors tests/config/test_discipline_corpus.py. Requires both provenance
    classes AND both dimensions to be represented, so a discovery-glob bug that
    silently drops half the matrix is caught here in normal CI.
    """
    assert _CASES, "no provenance-gate fixtures discovered"
    internal = [c for c in _CASES if c.expected["provenance"] == "internal"]
    external = [c for c in _CASES if c.expected["provenance"] == "external"]
    assert len(internal) >= 4, f"expected >=4 internal FP fixtures, got {len(internal)}"
    assert any(c.expected["dimension"] == "reliability" for c in external), "no reliability external control"
    assert any(c.expected["dimension"] == "security" for c in external), "no security external control"
    for case in _CASES:
        for key in ("dimension", "req", "display_file", "target_line", "construct", "provenance", "expectation"):
            assert key in case.expected, f"{case.name}: expected.json missing {key!r}"
        assert case.source_file.is_file(), f"{case.name}: source file missing at {case.source_file}"


@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_fixture_display_path_is_prod(case):
    """Fixture display paths must classify as PROD (no `(role:` toning-down label).

    ``_build_files_block`` appends ``(role: test_fixture)`` and tells the model
    to tone down findings for any path under ``**/fixtures/**``. The behavioral
    test avoids that confound by passing ``repo_root=<case>/repo`` so the display
    path renders as ``src/...`` (PROD). This pins that invariant: if it breaks,
    a de-escalation could come from the role label, not the gate.
    """
    assert path_role(case.expected["display_file"]) is Role.PROD


@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_fixture_construct_anchored_at_target_line(case):
    """The construct token must sit at the declared target line (catches fixture drift).

    If someone edits a vendored fixture (e.g. adds a guard) and the construct or
    line shifts, this fails in normal CI before the live test ever runs.
    """
    lines = case.source_file.read_text(encoding="utf-8").splitlines()
    target = case.expected["target_line"]
    construct = case.expected["construct"]
    window = "\n".join(lines[max(0, target - 3): target + 2])
    assert construct in window, (
        f"{case.name}: construct {construct!r} not found within +/-2 lines of "
        f"target_line {target} in {case.expected['display_file']}"
    )


@pytest.mark.parametrize(
    "case", [c for c in _CASES if c.expected["provenance"] == "internal"],
    ids=[c.name for c in _CASES if c.expected["provenance"] == "internal"],
)
def test_internal_fixture_prompt_has_no_role_label(case):
    """The assembled production prompt for an internal fixture must not tone down.

    Deterministic proof (no model) that the load-bearing repo_root choice keeps
    the fixture rendered as production code: the prompt must not contain a
    `(role:` label that would instruct the model to discount the finding.
    """
    prompt = assemble_api_prompt(
        source_files=[case.source_file],
        standards_text="",
        dimension=case.expected["dimension"],
        repo_name="provenance-gate-fixture",
        repo_root=case.repo_dir,
    )
    assert "(role:" not in prompt
    assert "test_fixture" not in prompt
