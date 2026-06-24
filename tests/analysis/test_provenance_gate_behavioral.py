"""Live behavioral regression for the critical-severity provenance gate (issue #641).

Run fa56db32 (model ``gemma4:26b-mlx``) rated 4 findings ``critical`` that are
false positives: the flagged value is provably INTERNAL (a defaulted prop/arg, a
SHA-256 cache key). PR #636 added a provenance gate to ``evaluation_rules.md`` so
those drop to ``major``/``minor`` while genuinely EXTERNAL input stays ``critical``.
Issue #638 verified this once by hand; this module makes the OUTCOME a durable matrix.

What this tier pins (and what it does NOT):
    It pins the OUTCOME on the real fixtures -- the known internal-provenance
    constructs never surface as ``critical`` (``test_internal_*``), and genuinely
    external input stays ``critical`` (``test_external_*``). It does NOT try to
    isolate the gate as the cause. We measured the gate-off counterfactual on a
    standard ``gemma4:26b``: with the provenance gate stripped, the four internal
    constructs still came back major / minor / not-flagged (only 1 of 12 runs was
    critical). A capable model does not reproduce these FPs even without the gate
    -- they were a ``gemma4:26b-mlx`` over-rating artifact, and the general
    severity rules already de-escalate them. So a gate-on/off behavioral A/B has
    no signal here; the gate's PRESENCE across every prompt path is guarded
    deterministically in ``test_prompt_provenance_gate.py`` (no model needed),
    and this tier guards that the corrected outcome holds on the real code.
    A run where the model drops an internal finding entirely is a pass -- the gate
    explicitly permits "major OR drop" for an internal value.

Faithfulness: this drives the exact local-provider path
(``assemble_api_prompt`` -> ``_call_api``) that ``subprocess.py`` uses. Downstream
enrichment only downweights confidence and never escalates severity, so the
emitted severity is a faithful, slightly conservative proxy for the full pipeline.

Opt-in: marked ``integration`` (excluded from the PR/publish ``-m "not integration"``
gates) and skipped unless a standard (non-mlx) ``gemma4:26b`` is reachable. The
``gemma4:26b-mlx`` build is compliance-blind (a known issue) and is explicitly
rejected. Run it locally::

    ollama serve &
    ollama pull gemma4:26b
    AI_MODEL=gemma4:26b uv run pytest \\
        tests/analysis/test_provenance_gate_behavioral.py -v -m integration
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("openai", reason="requires the openai SDK")

import quodeq
from quodeq.analysis._api_runner import ApiRunnerConfig, _call_api
from quodeq.analysis.api_prompt_assembly import assemble_api_prompt
from quodeq.analysis.subprocess import _load_standards_text
from quodeq.llm_bridge._ollama import get_ollama_status, list_ollama_models
from tests.analysis._provenance_gate_support import discover_cases, target_severity

# Standard build only. The mlx build is compliance-blind; reject it explicitly so
# a box that sourced quodeq.env (AI_MODEL=gemma4:26b-mlx) skips with a clear reason
# rather than running against the wrong model.
_GATE_MODEL = os.environ.get("AI_MODEL") or "gemma4:26b"
# Resolve the runner base from OLLAMA_BASE_URL so it targets the SAME server the
# readiness probe (_ollama.py, which also honours OLLAMA_BASE_URL) checks. When
# unset this is the standard local base, on which _call_api skips validate_url_safe.
_OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
_API_BASE = f"{_OLLAMA_BASE}/v1"

_RUNS_INTERNAL = int(os.environ.get("QGATE_RUNS_INTERNAL", "3"))
_RUNS_EXTERNAL = int(os.environ.get("QGATE_RUNS_EXTERNAL", "3"))
_MIN_VALID = 2  # need at least this many non-lossy runs to conclude

_COMPILED_DIR = Path(quodeq.__file__).parent / "data" / "standards" / "compiled"


def _gate_runnable() -> tuple[bool, str]:
    """(runnable, skip_reason). Probes are exception-safe and never raise."""
    if _GATE_MODEL.endswith("-mlx"):
        return False, (
            f"resolved AI_MODEL={_GATE_MODEL!r} is the compliance-blind mlx build; "
            "set AI_MODEL=gemma4:26b to exercise the gate's reasoning"
        )
    if not get_ollama_status().get("running"):
        return False, "ollama server not reachable on the configured base URL"
    names = {m["name"] for m in list_ollama_models()}
    if _GATE_MODEL not in names:
        return False, f"required model {_GATE_MODEL!r} not pulled (installed: {sorted(names)})"
    return True, ""


_RUNNABLE, _SKIP_REASON = _gate_runnable()

pytestmark = [
    pytest.mark.integration,
    # Overrides the 60s global. A test makes _RUNS_* calls, each read-bounded at
    # _LOCAL_TIMEOUT (500s) in _call_api; 3000s covers the pathological all-slow
    # case without the marker killing a working run early.
    pytest.mark.timeout(3000),
    pytest.mark.skipif(not _RUNNABLE, reason=f"provenance-gate live test skipped: {_SKIP_REASON}"),
]

_CASES = discover_cases()
_INTERNAL = [c for c in _CASES if c.expected["provenance"] == "internal"]
_EXTERNAL = [c for c in _CASES if c.expected["provenance"] == "external"]


def _run(case):
    """One production-path model call. Returns (target_severity|None, was_lossy)."""
    dimension = case.expected["dimension"]
    standards = _load_standards_text(_COMPILED_DIR, dimension)
    prompt = assemble_api_prompt(
        source_files=[case.source_file],
        standards_text=standards,
        dimension=dimension,
        repo_name="provenance-gate-fixture",
        repo_root=case.repo_dir,
    )
    # Fail fast on the role-label confound: the production path must render the
    # fixture as PROD code (no "tone down" label), else a de-escalation could come
    # from the role label rather than the gate.
    assert "(role:" not in prompt, f"{case.name}: fixture rendered with a role label (wrong repo_root)"
    findings, lossy = _call_api(prompt, ApiRunnerConfig(model=_GATE_MODEL, api_base=_API_BASE, temperature=0.1))
    # Loose req-only matching is for the single-issue external fixtures; internal
    # fixtures hold other same-req sites, so they match on construct/line only.
    allow_req_only = case.expected["provenance"] == "external"
    severity, _matches = target_severity(findings, case.expected, allow_req_only=allow_req_only)
    return severity, lossy


@pytest.mark.parametrize("case", _INTERNAL, ids=[c.name for c in _INTERNAL])
def test_internal_construct_not_critical(case):
    """A known internal-provenance FP must never surface as critical.

    Outcome pin on the #638 result. Absence of a finding is a pass (the gate
    permits "major OR drop" for an internal value); the only failure is a
    critical re-appearing on the construct.
    """
    runs = [_run(case) for _ in range(_RUNS_INTERNAL)]
    valid = [s for (s, lossy) in runs if not lossy]
    if len(valid) < _MIN_VALID:
        pytest.skip(f"{case.name}: too many lossy runs ({len(valid)} valid); model unstable")
    crit = sum(1 for s in valid if s == "critical")
    assert crit == 0, (
        f"{case.name}: REGRESSION - an internal-provenance construct came back "
        f"critical in {crit}/{len(valid)} runs; it must stay <= major.\n  severities: {valid}"
    )


@pytest.mark.parametrize("case", _EXTERNAL, ids=[c.name for c in _EXTERNAL])
def test_external_construct_stays_critical(case):
    """External (attacker-controlled) input must stay critical: the gate must not over-relax.

    Unlike the internal cases, here a finding is expected -- a MISSING critical is
    the regression (the gate's carve-out leaking onto genuinely external input).
    """
    runs = [_run(case) for _ in range(_RUNS_EXTERNAL)]
    valid = [s for (s, lossy) in runs if not lossy]
    if len(valid) < _MIN_VALID:
        pytest.skip(f"{case.name}: too many lossy runs ({len(valid)} valid); model unstable")
    crit = sum(1 for s in valid if s == "critical")
    majority = len(valid) // 2 + 1
    assert crit >= majority, (
        f"{case.name}: the gate OVER-RELAXED an external case - critical in only "
        f"{crit}/{len(valid)} runs (need {majority}). Attacker-controlled input must "
        f"stay critical.\n  severities: {valid}"
    )
