"""Mock OpenAI clients and finding payloads shared by the test_api_runner* siblings."""
from __future__ import annotations

import json
from unittest.mock import MagicMock


def _mock_raw_client_finish(content: str, finish_reason: str) -> MagicMock:
    """Mock client whose single choice carries an explicit finish_reason."""
    msg = MagicMock(content=content)
    choice = MagicMock(message=msg, finish_reason=finish_reason)
    response = MagicMock(choices=[choice])
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


def _make_findings_json(*findings_data) -> str:
    """Build a JSON string of findings from (req, t, file, line, severity, w) tuples."""
    findings = []
    for req, t, file, line, severity, w in findings_data:
        findings.append({
            "req": req, "t": t, "file": file, "line": line,
            "severity": severity, "w": w,
            "snippet": f"line for {req}",
            "reason": f"Test reason for {req}",
        })
    return json.dumps({"findings": findings})


def _mock_raw_client(content: str) -> MagicMock:
    """Build a mock that mimics the raw OpenAI client context manager returning a response."""
    msg = MagicMock(content=content)
    choice = MagicMock(message=msg)
    response = MagicMock(choices=[choice])
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client
