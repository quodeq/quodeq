import json
from pathlib import Path

from quodeq_bench.evidence import (
    Finding,
    find_evidence_dir,
    load_findings,
    parse_cwe_refs,
)

_VIOLATION = {
    "schema_version": 1,
    "p": "Confidentiality",
    "t": "violation",
    "d": "security",
    "w": "SQL injection via f-string",
    "file": "app.py",
    "line": 13,
    "snippet": 'query = f"SELECT * FROM users WHERE id = {user_id}"',
    "severity": "critical",
    "reason": "User input concatenated into SQL.",
    "req": "S-CON-1",
    "vt": "sql-injection",
    "refs": ["CWE-89", "OWASP-A03"],
}
_COMPLIANCE = dict(_VIOLATION, t="compliance", w="parameterized query", line=5)
_MARKER_OK = {"_marker": "file_done", "file": "app.py", "status": "ok"}
_MARKER_ERR = {"_marker": "file_done", "file": "broken.py", "status": "error"}


def _write_evidence(tmp_path: Path) -> Path:
    evidence = tmp_path / "run" / "evidence"
    evidence.mkdir(parents=True)
    lines = [_VIOLATION, _COMPLIANCE, _MARKER_OK, _MARKER_ERR]
    (evidence / "security_evidence.jsonl").write_text(
        "\n".join(json.dumps(obj) for obj in lines) + "\n", encoding="utf-8"
    )
    return evidence


def test_parse_cwe_refs() -> None:
    assert parse_cwe_refs(["CWE-89", "OWASP-A03", "cwe-798"]) == (89, 798)


def test_load_findings_skips_markers_and_compliance(tmp_path: Path) -> None:
    findings, errored = load_findings(_write_evidence(tmp_path))
    assert len(findings) == 1
    assert findings[0] == Finding(
        dimension="security",
        file="app.py",
        line=13,
        severity="critical",
        req="S-CON-1",
        vt="sql-injection",
        refs=("CWE-89", "OWASP-A03"),
        title="SQL injection via f-string",
    )
    assert errored == ["broken.py"]


def test_load_findings_tolerates_malformed_lines(tmp_path: Path) -> None:
    evidence = _write_evidence(tmp_path)
    path = evidence / "security_evidence.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "{not json\n", encoding="utf-8")
    findings, _ = load_findings(evidence)
    assert len(findings) == 1


def test_find_evidence_dir(tmp_path: Path) -> None:
    evidence = _write_evidence(tmp_path)
    assert find_evidence_dir(tmp_path) == evidence
    assert find_evidence_dir(tmp_path / "nowhere") is None
