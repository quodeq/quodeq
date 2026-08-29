"""Parity between the live scan counter and the persisted run report.

The live counter (``tally_unique_findings``, read by the heartbeat and by
``services.scan_progress``) and the report path (``_group_judgments``, which
builds the per-dimension evaluation JSON) read the same evidence JSONL. Only
the report path used to apply the standard-membership predicate, so a finding
whose principle is not in the dimension's standard was counted live but
quarantined out of the report — a visible off-by-N in the UI.

Regression case: run 8fc08558 of project d33f1fd0 had 571 unique maintainability
violations in the JSONL and 570 in evaluation/maintainability.json. The extra row
carried no ``p`` and ``req: "N/A"``, so it resolved to the phantom principle
"N/A", which the standard does not define.

These tests pin the invariant by running BOTH paths over one input and comparing,
rather than asserting hand-computed constants.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.analysis.subagents.jsonl_utils import tally_unique_findings
from quodeq.core.evidence._jsonl import parse_jsonl_line
from quodeq.core.evidence._req_mapping import _group_judgments, build_principle_resolver
from quodeq.data.fs.standards_loader import read_req_to_principle_map

_DIMENSION = "demo"


@pytest.fixture
def compiled_dir(tmp_path: Path) -> Path:
    """A compiled standard defining one principle with two requirements."""
    d = tmp_path / "compiled"
    d.mkdir()
    (d / f"{_DIMENSION}.json").write_text(json.dumps({
        "id": _DIMENSION,
        "name": "Demo",
        "principles": [{
            "name": "Analyzability",
            "requirements": [{"id": "D-ANA-1"}, {"id": "D-ANA-2"}],
        }],
    }), encoding="utf-8")
    return d


def _rows() -> list[dict]:
    """Four unique violations + one compliance; exactly one is unmappable."""
    return [
        # Mappable: `p` already carries the principle name (the common shape).
        {"p": "Analyzability", "req": "D-ANA-1", "t": "violation",
         "d": _DIMENSION, "file": "a.py", "line": 1},
        {"p": "Analyzability", "req": "D-ANA-2", "t": "violation",
         "d": _DIMENSION, "file": "b.py", "line": 2},
        # Mappable via the req -> principle map: `p` carries a requirement ID.
        {"p": "D-ANA-1", "t": "violation", "d": _DIMENSION, "file": "c.py", "line": 3},
        # Unmappable: no `p`, and `req` is the phantom "N/A" principle. This is
        # the row the report quarantines and the live counter used to count.
        {"req": "N/A", "t": "violation", "d": _DIMENSION,
         "file": "d.py", "line": 4, "severity": "critical"},
        {"p": "Analyzability", "req": "D-ANA-1", "t": "compliance",
         "d": _DIMENSION, "file": "e.py", "line": 5},
    ]


@pytest.fixture
def evidence(tmp_path: Path) -> Path:
    p = tmp_path / f"{_DIMENSION}_evidence.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in _rows()), encoding="utf-8")
    return p


def _report_violation_count(evidence_path: Path, compiled: Path) -> int:
    """Violations the report path keeps, via the real grouping code."""
    judgments = []
    for line in evidence_path.read_text(encoding="utf-8").splitlines():
        parsed = parse_jsonl_line(line)
        if parsed is not None:
            judgments.append(parsed[0])
    grouped = _group_judgments(judgments, dimension=_DIMENSION, compiled_dir=compiled,
                               req_map_reader=read_req_to_principle_map)
    return sum(len(v) for v in grouped.violations.values())


def test_live_counter_matches_report_violation_count(evidence, compiled_dir):
    """The invariant: both paths agree on how many violations exist."""
    resolver = build_principle_resolver(_DIMENSION, compiled_dir=compiled_dir,
                                        req_map_reader=read_req_to_principle_map)
    tally = tally_unique_findings(evidence, resolver=resolver)
    assert tally.violations == _report_violation_count(evidence, compiled_dir)


def test_unmappable_finding_is_counted_as_quarantined_not_dropped(evidence, compiled_dir):
    """Excluded from the violation count, but carried so it is not lost."""
    resolver = build_principle_resolver(_DIMENSION, compiled_dir=compiled_dir,
                                        req_map_reader=read_req_to_principle_map)
    tally = tally_unique_findings(evidence, resolver=resolver)
    assert tally.violations == 3
    assert tally.quarantined == 1
    assert tally.compliance == 1


def test_without_resolver_the_tally_stays_permissive(evidence):
    """No standard available means no predicate to apply: count everything."""
    tally = tally_unique_findings(evidence)
    assert tally.violations == 4
    assert tally.quarantined == 0


def test_duplicates_are_folded_before_the_quarantine_check(tmp_path, compiled_dir):
    """A repeated unmappable row is one quarantined finding, not N."""
    p = tmp_path / "ev.jsonl"
    line = json.dumps({"req": "N/A", "t": "violation", "d": _DIMENSION,
                       "file": "d.py", "line": 4})
    p.write_text((line + "\n") * 3, encoding="utf-8")
    resolver = build_principle_resolver(_DIMENSION, compiled_dir=compiled_dir,
                                        req_map_reader=read_req_to_principle_map)
    tally = tally_unique_findings(p, resolver=resolver)
    assert tally.quarantined == 1
    assert tally.duplicates == 2
    assert tally.violations == 0


def test_resolver_without_a_standard_maps_everything_through(tmp_path):
    """An empty canonical set stays permissive rather than quarantining all."""
    resolver = build_principle_resolver(_DIMENSION, compiled_dir=tmp_path / "absent")
    assert resolver.resolve("anything") == "anything"
