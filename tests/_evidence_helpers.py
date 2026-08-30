"""Shared evidence test helpers (formerly tests/engine/conftest.py).

Pure module: only json + quodeq.core.evidence.model. Analysis-layer helpers
(_fake_run_analysis, _run_server) live in tests/_analysis_helpers.py so that
tests/core consumers of _evidence_line/make_evidence_with_confidence stay
decoupled from the analysis layer and its framework dependencies.
"""
from __future__ import annotations

import json

from quodeq.core.evidence.model import Evidence, PrincipleEvidence

_TEST_PRINCIPLE = "ts-001"
_TEST_DIMENSION = "security"
_TEST_SEVERITY = "high"
_TEST_SNIPPET = "eval(x)"
_TEST_REASON = "injection"


def _make_request(method: str, req_id: int = 1, params: dict | None = None) -> str:
    """Build a JSON-RPC request string."""
    msg: dict = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg)


def _evidence_line(**overrides) -> str:
    """Build a JSONL evidence line with sensible defaults."""
    obj = {
        "p": _TEST_PRINCIPLE,
        "t": "violation",
        "d": _TEST_DIMENSION,
        "w": "eval usage",
        "file": "src/app.ts",
        "line": 10,
        "snippet": "eval(userInput)",
        "severity": _TEST_SEVERITY,
        "vt": "code-injection",
        "reason": "eval is dangerous",
    }
    obj.update(overrides)
    return json.dumps(obj)


def make_evidence_with_confidence(
    confidence_level="high",
    violations=None,
    compliance=None,
    n_violations=1,
    n_compliance=2,
):
    """Build Evidence with explicit confidence level and finding counts."""
    viol = violations or [
        {"file": f"v{i}.ts", "line": i, "snippet": _TEST_SNIPPET, "reason": _TEST_REASON, "severity": _TEST_SEVERITY, "vt": "code-injection"}
        for i in range(n_violations)
    ]
    comp = compliance or [
        {"file": f"c{i}.ts", "line": i, "snippet": "JSON.parse(x)", "reason": "safe"}
        for i in range(n_compliance)
    ]
    total = len(viol) + len(comp)
    pct = round(len(comp) / total * 100, 1) if total > 0 else 0.0
    pe = PrincipleEvidence(
        practice_id=_TEST_PRINCIPLE,
        display_name="Avoid eval()",
        dimension=_TEST_DIMENSION,
        severity=_TEST_SEVERITY,
        violations=viol,
        compliance=comp,
        metrics={
            "total_instances": total,
            "compliant": len(comp),
            "violating": len(viol),
            "compliance_percentage": pct,
            "confidence_level": confidence_level,
            "is_balanced": len(viol) > 0 and len(comp) > 0,
        },
    )
    return Evidence(
        repository="test-repo",
        language="typescript",
        date="2026-03-03",
        source_file_count=100,
        files_read=50,
        coverage_pct=50.0,
        principles={_TEST_PRINCIPLE: pe},
    )
