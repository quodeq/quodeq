"""Replayed cache findings are re-admitted with the run's standards.

A cache entry can predate its standard, or have been written while the
standard was not loaded, so it may carry a requirement code and no principle.
Replay places every finding through admission: the evidence row and the
event agree, and a finding the standard cannot place becomes an unmapped row
that never reaches the event log. The cache entry itself stays as it was.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace

from quodeq.analysis.cache.dimension_helpers import ClassifyResult
from quodeq.analysis.cache.dimension_runner import (
    ReplayPolicy,
    replay_catalog_loader,
    write_findings,
)

DIM = "accessibility"


def _standard(directory: Path, principle: str = "Perceivable") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{DIM}.json").write_text(json.dumps({"id": DIM, "principles": [
        {"name": principle, "requirements": [{"id": "ACC-PER-01"}]},
        {"name": "Operable", "requirements": [{"id": "ACC-OPR-01"}]},
    ]}), encoding="utf-8")
    return directory


def _finding(req: str, principle: str | None = None) -> dict:
    row = {
        "file": "a.kt", "line": 1, "t": "compliance", "w": "t", "d": DIM,
        "req": req, "severity": "minor", "snippet": "x", "reason": "r",
    }
    if principle is not None:
        row["p"] = principle
    return row


def _replay(tmp_path: Path, findings: list[dict]) -> tuple[list[dict], list[dict]]:
    standards = tmp_path / "standards"
    _standard(standards / "compiled")
    config = SimpleNamespace(standards_dir=standards, evaluators_dir=None)
    (tmp_path / "evidence").mkdir()
    jsonl = tmp_path / "evidence" / f"{DIM}_evidence.jsonl"
    classify = ClassifyResult(cached_findings=findings, unconsolidated_findings=[])

    write_findings(jsonl, classify, append=False,
                   policy=ReplayPolicy(catalog_loader=replay_catalog_loader(config)))

    rows = [json.loads(line) for line in jsonl.read_text().splitlines()]
    events_path = tmp_path / "events.jsonl"
    events = [json.loads(line)["payload"] for line in events_path.read_text().splitlines()] \
        if events_path.exists() else []
    return rows, events


def test_a_finding_without_a_principle_is_placed_in_the_row_and_the_event(tmp_path: Path) -> None:
    rows, events = _replay(tmp_path, [_finding("ACC-PER-01"), _finding("acc-opr-1")])

    assert [(r["p"], r["req"]) for r in rows] == [("Perceivable", "ACC-PER-01"), ("Operable", "ACC-OPR-01")]
    assert [e["practice_id"] for e in events] == ["Perceivable", "Operable"]
    assert all(r["carried_forward"] for r in rows)


def test_a_stale_principle_is_replaced_by_the_standards(tmp_path: Path) -> None:
    rows, events = _replay(tmp_path, [_finding("ACC-PER-01", principle="Renamed Long Ago")])

    assert rows[0]["p"] == "Perceivable" and events[0]["practice_id"] == "Perceivable"


def test_an_unknown_code_is_kept_as_unmapped_and_never_emitted(tmp_path: Path, caplog) -> None:
    with caplog.at_level(logging.WARNING):
        rows, events = _replay(tmp_path, [_finding("ZZZ-NOPE-99"), _finding("ZZZ-NOPE-98")])

    assert [r["admission"] for r in rows] == ["unmapped", "unmapped"]
    assert events == []
    assert "2" in caplog.text and DIM in caplog.text


def test_the_cache_owned_dicts_are_not_mutated(tmp_path: Path) -> None:
    original = _finding("ACC-PER-01")

    _replay(tmp_path, [original])

    assert "p" not in original and "carried_forward" not in original


def test_a_custom_evaluator_wins_over_the_built_in(tmp_path: Path) -> None:
    standards = tmp_path / "standards"
    _standard(standards / "compiled")
    evaluators = _standard(tmp_path / "evaluators", principle="Override")
    config = SimpleNamespace(standards_dir=standards, evaluators_dir=evaluators)

    catalog = replay_catalog_loader(config)([DIM])

    assert catalog.get(DIM).req_to_principle["ACC-PER-01"] == "Override"


def test_an_unknown_code_with_a_valid_principle_keeps_counting_under_it(tmp_path: Path) -> None:
    rows, events = _replay(tmp_path, [_finding("ACC-PER-99", principle="Operable")])

    assert rows[0]["p"] == "Operable" and rows[0]["req_unknown"] is True
    assert [e["practice_id"] for e in events] == ["Operable"]
