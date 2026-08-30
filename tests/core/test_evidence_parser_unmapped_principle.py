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
from pathlib import Path

from quodeq.core.evidence._req_mapping import QuarantinedFinding, _group_judgments
from quodeq.core.evidence.parser import (
    EvidenceContext,
    parse_jsonl_to_evidence,
    parse_jsonl_to_evidence_by_dimension,
)
from quodeq.core.events.models import Judgment


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


def _read_map(directory: Path, dimension: str) -> dict[str, str]:
    """Inline stand-in for data.fs.standards_loader.read_req_to_principle_map,
    so this core-layer test injects the reader without importing the adapter."""
    path = directory / f"{dimension}.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        req.get("id", ""): principle.get("name", "")
        for principle in data.get("principles", [])
        for req in principle.get("requirements", [])
        if req.get("id") and principle.get("name")
    }


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

    result = parse_jsonl_to_evidence_by_dimension(jsonl, _ctx(), evaluators_dir=compiled,
                                                   req_map_reader=_read_map)

    maint = result["maintainability"]
    assert "N/A" not in maint.principles
    assert set(maint.principles.keys()) == {"Modularity"}


def test_unmappable_finding_is_reported_to_quarantine_sink(tmp_path):
    compiled = tmp_path / "compiled"
    _write_compiled_standard(compiled, "maintainability", {"Modularity": ["M-MOD-1"]})
    jsonl = tmp_path / "evidence.jsonl"
    jsonl.write_text(json.dumps({
        "schema_version": 1, "d": "maintainability", "t": "violation",
        "req": "N/A", "file": "c.py", "line": 1, "w": "arbitrary file read",
        "severity": "critical", "snippet": "x",
    }) + "\n", encoding="utf-8")

    captured: list[list[QuarantinedFinding]] = []
    parse_jsonl_to_evidence_by_dimension(
        jsonl, _ctx(), evaluators_dir=compiled, req_map_reader=_read_map,
        on_quarantine=captured.append,
    )

    assert len(captured) == 1
    findings = captured[0]
    assert len(findings) == 1
    assert findings[0].dimension == "maintainability"
    assert findings[0].file == "c.py"
    assert findings[0].severity == "critical"


def test_empty_evaluators_dir_falls_back_to_compiled_standard(tmp_path):
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

    captured: list[list[QuarantinedFinding]] = []
    result = parse_jsonl_to_evidence_by_dimension(
        jsonl, _ctx(), compiled_dir=compiled, evaluators_dir=evaluators,
        req_map_reader=_read_map, on_quarantine=captured.append,
    )

    maint = result["maintainability"]
    assert "N/A" not in maint.principles
    assert set(maint.principles.keys()) == {"Modularity"}
    all_violations = [v for pe in maint.principles.values() for v in pe.violations]
    assert not any(v.get("req") == "N/A" for v in all_violations)
    assert len(captured) == 1 and len(captured[0]) == 1
    assert captured[0][0].file == "c.py"


def test_quarantined_findings_count_matches_quarantined_counter(tmp_path):
    """`quarantined_findings` is per-judgment detail behind the `quarantined`
    counter -- no dedup, no set, no filter. Two duplicate-looking findings
    (same practice_id, same file) must both survive as separate entries."""
    compiled = tmp_path / "compiled"
    _write_compiled_standard(compiled, "maintainability", {"Modularity": ["M-MOD-1"]})
    judgments = [
        Judgment(practice_id="N/A", verdict="violation", dimension="maintainability",
                 file="c.py", line=1, reason="x", severity="critical"),
        Judgment(practice_id="N/A", verdict="violation", dimension="maintainability",
                 file="c.py", line=1, reason="x", severity="critical"),
        Judgment(practice_id="Modularity", verdict="violation", dimension="maintainability",
                 req="M-MOD-1", file="b.py", line=10, reason="x", severity="major"),
    ]
    grouped = _group_judgments(
        judgments, dimension="maintainability",
        req_map_reader=_read_map, evaluators_dir=compiled,
    )

    assert grouped.quarantined == 2
    assert len(grouped.quarantined_findings) == grouped.quarantined


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
        req_map_reader=_read_map,
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
        req_map_reader=_read_map,
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
        req_map_reader=_read_map,
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
