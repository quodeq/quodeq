"""Tests for loading violations directly from evidence JSONL."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.ci._evidence_reader import load_violations_from_evidence


def _write_jsonl(path: Path, lines: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")


def test_reads_violations_only(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    _write_jsonl(evidence_dir / "security_evidence.jsonl", [
        {"p": "SEC-01", "t": "violation", "d": "security",
         "file": "app.py", "line": 12, "severity": "high",
         "reason": "hardcoded secret", "w": "Hardcoded token"},
        {"p": "SEC-02", "t": "compliance", "d": "security",
         "file": "ok.py", "line": 5},
    ])
    result = load_violations_from_evidence(evidence_dir)
    assert len(result) == 1
    v = result[0]
    assert v["file"] == "app.py"
    assert v["line"] == 12
    assert v["severity"] == "high"
    assert v["title"] == "Hardcoded token"


def test_multiple_dimensions_aggregated(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    _write_jsonl(evidence_dir / "security_evidence.jsonl", [
        {"p": "SEC", "t": "violation", "d": "security",
         "file": "a.py", "line": 1, "severity": "high"},
    ])
    _write_jsonl(evidence_dir / "reliability_evidence.jsonl", [
        {"p": "REL", "t": "violation", "d": "reliability",
         "file": "b.py", "line": 2, "severity": "medium"},
    ])
    result = load_violations_from_evidence(evidence_dir)
    assert len(result) == 2
    files = {v["file"] for v in result}
    assert files == {"a.py", "b.py"}


def test_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert load_violations_from_evidence(tmp_path / "nope") == []


def test_skips_malformed_lines(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "security_evidence.jsonl").write_text(
        'not-json\n'
        '{"p": "SEC", "t": "violation", "d": "security", "file": "x.py", "line": 1}\n'
    )
    result = load_violations_from_evidence(evidence_dir)
    assert len(result) == 1
    assert result[0]["file"] == "x.py"
