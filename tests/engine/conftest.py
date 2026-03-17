"""Shared test helpers for engine tests."""
from __future__ import annotations

import json
import sys
from io import StringIO
from unittest.mock import patch

from quodeq.engine import mcp_findings
from quodeq.core.evidence.model import Evidence, PrincipleEvidence


def _make_request(method: str, req_id: int = 1, params: dict | None = None) -> str:
    """Build a JSON-RPC request string."""
    msg: dict = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg)


def _run_server(input_lines: list[str], findings_file: str) -> list[dict]:
    """Feed *input_lines* to the MCP server and return parsed response dicts."""
    stdin_text = "\n".join(input_lines) + "\n"
    stdout_buf = StringIO()
    with patch.object(sys, "stdin", StringIO(stdin_text)), \
         patch.object(sys, "stdout", stdout_buf), \
         patch.object(sys, "argv", ["mcp_findings.py", findings_file]):
        mcp_findings.main()
    output = stdout_buf.getvalue().strip()
    return [json.loads(line) for line in output.splitlines() if line.strip()]


def _evidence_line(**overrides) -> str:
    """Build a JSONL evidence line with sensible defaults."""
    obj = {
        "p": "ts-001",
        "t": "violation",
        "d": "security",
        "w": "eval usage",
        "file": "src/app.ts",
        "line": 10,
        "snippet": "eval(userInput)",
        "severity": "high",
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
        {"file": f"v{i}.ts", "line": i, "snippet": "eval(x)", "reason": "injection", "severity": "high", "vt": "code-injection"}
        for i in range(n_violations)
    ]
    comp = compliance or [
        {"file": f"c{i}.ts", "line": i, "snippet": "JSON.parse(x)", "reason": "safe"}
        for i in range(n_compliance)
    ]
    total = len(viol) + len(comp)
    pct = round(len(comp) / total * 100, 1) if total > 0 else 0.0
    pe = PrincipleEvidence(
        practice_id="ts-001",
        display_name="Avoid eval()",
        dimension="security",
        severity="high",
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
        principles={"ts-001": pe},
    )
