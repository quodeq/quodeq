"""A finding whose principle is not in the dimension's standard must not
become a phantom principle. It is quarantined (excluded from principle
grouping) and logged so a misfiled critical is never silently lost.

Regression for the dashboard showing a 6th maintainability principle named
"N/A": a critical security finding was emitted under maintainability with an
unresolvable requirement (req="N/A"), and the raw "N/A" string was grouped as
its own principle.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from quodeq.core.evidence.parser import (
    EvidenceContext,
    parse_jsonl_to_evidence,
    parse_jsonl_to_evidence_by_dimension,
)


def _write_compiled_standard(
    compiled_dir: Path, dimension: str, principles: dict[str, list[str]],
) -> None:
    """Write a minimal compiled standard: principle name -> requirement ids."""
    compiled_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "id": dimension,
        "name": dimension,
        "principles": [
            {"name": name, "requirements": [{"id": rid} for rid in reqs]}
            for name, reqs in principles.items()
        ],
    }
    (compiled_dir / f"{dimension}.json").write_text(json.dumps(data), encoding="utf-8")


def _ctx() -> EvidenceContext:
    return EvidenceContext(
        language="python", repository="t", date_str="2026-06-29",
        source_file_count=10, files_read=2,
    )


def test_unmappable_finding_not_grouped_as_phantom_principle(tmp_path):
    compiled = tmp_path / "compiled"
    _write_compiled_standard(compiled, "maintainability", {
        "Modularity": ["M-MOD-1"],
        "Testability": ["M-TST-1"],
    })
    jsonl = tmp_path / "evidence.jsonl"
    findings = [
        {"schema_version": 1, "p": "Modularity", "d": "maintainability", "t": "violation",
         "req": "M-MOD-1", "file": "b.py", "line": 10, "w": "high complexity",
         "severity": "major", "snippet": "def big(): ..."},
        # Orphan: no principle, req does not resolve -> practice_id becomes "N/A"
        {"schema_version": 1, "d": "maintainability", "t": "violation",
         "req": "N/A", "file": "c.py", "line": 1, "w": "arbitrary file read",
         "severity": "critical", "snippet": "open(os.environ['X'])"},
    ]
    jsonl.write_text("\n".join(json.dumps(f) for f in findings) + "\n", encoding="utf-8")

    result = parse_jsonl_to_evidence_by_dimension(jsonl, _ctx(), evaluators_dir=compiled)

    maint = result["maintainability"]
    assert "N/A" not in maint.principles
    assert set(maint.principles.keys()) == {"Modularity"}


def test_unmappable_finding_is_logged(tmp_path, caplog):
    compiled = tmp_path / "compiled"
    _write_compiled_standard(compiled, "maintainability", {"Modularity": ["M-MOD-1"]})
    jsonl = tmp_path / "evidence.jsonl"
    jsonl.write_text(json.dumps({
        "schema_version": 1, "d": "maintainability", "t": "violation",
        "req": "N/A", "file": "c.py", "line": 1, "w": "arbitrary file read",
        "severity": "critical", "snippet": "x",
    }) + "\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        parse_jsonl_to_evidence_by_dimension(jsonl, _ctx(), evaluators_dir=compiled)

    assert any(
        "N/A" in r.getMessage() or "unmapped" in r.getMessage().lower()
        for r in caplog.records
    )


def test_empty_evaluators_dir_falls_back_to_compiled_standard(tmp_path, caplog):
    """Production config: ~/.quodeq/evaluators exists but is EMPTY and the
    built-in standard lives only in standards/compiled/<dim>.json. The
    quarantine must fall back to the compiled standard instead of silently
    going permissive. Regression for run 03c99d26 (quodeq 1.5.2): a phantom
    "N/A" principle plus a principle="N/A" critical were written into
    evaluation/maintainability.json despite the write-time guard."""
    compiled = tmp_path / "standards" / "compiled"
    _write_compiled_standard(compiled, "maintainability", {
        "Modularity": ["M-MOD-1"],
        "Testability": ["M-TST-1"],
    })
    evaluators = tmp_path / "evaluators"
    evaluators.mkdir()  # exists but holds no standards — the real-install shape
    jsonl = tmp_path / "evidence.jsonl"
    findings = [
        {"schema_version": 1, "p": "Modularity", "d": "maintainability", "t": "violation",
         "req": "M-MOD-1", "file": "b.py", "line": 10, "w": "high complexity",
         "severity": "major", "snippet": "def big(): ..."},
        {"schema_version": 1, "d": "maintainability", "t": "violation",
         "req": "N/A", "file": "c.py", "line": 73, "w": "arbitrary file read",
         "severity": "critical", "snippet": "open(os.environ['X'])"},
    ]
    jsonl.write_text("\n".join(json.dumps(f) for f in findings) + "\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        result = parse_jsonl_to_evidence_by_dimension(
            jsonl, _ctx(), compiled_dir=compiled, evaluators_dir=evaluators,
        )

    maint = result["maintainability"]
    assert "N/A" not in maint.principles
    assert set(maint.principles.keys()) == {"Modularity"}
    all_violations = [v for pe in maint.principles.values() for v in pe.violations]
    assert not any(v.get("req") == "N/A" for v in all_violations)
    assert any("Quarantining" in r.getMessage() for r in caplog.records)


def test_single_dimension_parse_falls_back_to_compiled_standard(tmp_path):
    """parse_jsonl_to_evidence (the per-dimension analysis path) must apply the
    same compiled-standard fallback as the by-dimension variant."""
    compiled = tmp_path / "standards" / "compiled"
    _write_compiled_standard(compiled, "maintainability", {"Modularity": ["M-MOD-1"]})
    evaluators = tmp_path / "evaluators"
    evaluators.mkdir()
    jsonl = tmp_path / "evidence.jsonl"
    findings = [
        {"schema_version": 1, "p": "Modularity", "d": "maintainability", "t": "violation",
         "req": "M-MOD-1", "file": "b.py", "line": 10, "w": "x",
         "severity": "major", "snippet": "y"},
        {"schema_version": 1, "d": "maintainability", "t": "violation",
         "req": "N/A", "file": "c.py", "line": 1, "w": "z",
         "severity": "critical", "snippet": "w"},
    ]
    jsonl.write_text("\n".join(json.dumps(f) for f in findings) + "\n", encoding="utf-8")

    evidence = parse_jsonl_to_evidence(
        jsonl, _ctx(), compiled_dir=compiled, evaluators_dir=evaluators,
    )

    assert "N/A" not in evidence.principles
    assert set(evidence.principles.keys()) == {"Modularity"}


def test_custom_evaluator_standard_takes_precedence_over_compiled(tmp_path):
    """When the evaluators dir HAS a standard for the dimension, it is
    authoritative: the compiled built-in standard is not consulted."""
    compiled = tmp_path / "standards" / "compiled"
    _write_compiled_standard(compiled, "maintainability", {"Modularity": ["M-MOD-1"]})
    evaluators = tmp_path / "evaluators"
    _write_compiled_standard(evaluators, "maintainability", {"CustomP": ["C-1"]})
    jsonl = tmp_path / "evidence.jsonl"
    findings = [
        {"schema_version": 1, "p": "CustomP", "d": "maintainability", "t": "violation",
         "req": "C-1", "file": "a.py", "line": 1, "w": "x",
         "severity": "minor", "snippet": "y"},
        # In the compiled standard but not the custom one -> quarantined
        {"schema_version": 1, "p": "Modularity", "d": "maintainability", "t": "violation",
         "req": "M-MOD-1", "file": "b.py", "line": 2, "w": "x",
         "severity": "minor", "snippet": "y"},
    ]
    jsonl.write_text("\n".join(json.dumps(f) for f in findings) + "\n", encoding="utf-8")

    result = parse_jsonl_to_evidence_by_dimension(
        jsonl, _ctx(), compiled_dir=compiled, evaluators_dir=evaluators,
    )

    assert set(result["maintainability"].principles.keys()) == {"CustomP"}


def test_permissive_when_neither_source_has_standard(tmp_path):
    """Both dirs supplied but neither holds a standard for the dimension:
    the guard must stay permissive and group by the raw principle."""
    compiled = tmp_path / "standards" / "compiled"
    compiled.mkdir(parents=True)
    evaluators = tmp_path / "evaluators"
    evaluators.mkdir()
    jsonl = tmp_path / "evidence.jsonl"
    jsonl.write_text(json.dumps({
        "schema_version": 1, "p": "Modularity", "d": "maintainability", "t": "violation",
        "req": "M-MOD-1", "file": "a.py", "line": 1, "w": "x", "severity": "minor",
        "snippet": "y",
    }) + "\n", encoding="utf-8")

    result = parse_jsonl_to_evidence_by_dimension(
        jsonl, _ctx(), compiled_dir=compiled, evaluators_dir=evaluators,
    )

    assert set(result["maintainability"].principles.keys()) == {"Modularity"}


def test_no_standard_keeps_all_principles(tmp_path):
    """Without a standard (no evaluators_dir) the guard must stay permissive,
    grouping by raw principle so legacy/standard-less callers are unaffected."""
    jsonl = tmp_path / "evidence.jsonl"
    jsonl.write_text(json.dumps({
        "schema_version": 1, "p": "Modularity", "d": "maintainability", "t": "violation",
        "req": "M-MOD-1", "file": "a.py", "line": 1, "w": "x", "severity": "minor",
        "snippet": "y",
    }) + "\n", encoding="utf-8")

    result = parse_jsonl_to_evidence_by_dimension(jsonl, _ctx())

    assert set(result["maintainability"].principles.keys()) == {"Modularity"}
