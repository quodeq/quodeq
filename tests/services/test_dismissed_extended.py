"""Extended tests for dismissed findings -- restore_all, recount_totals, filter_dismissed."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.data.events.writer import EventLogWriter
from quodeq.core.types.finding import Finding, SeverityTally, Totals
from quodeq.data.projection.projector import Projector
from quodeq.services.dismissed import (
    dismiss_finding,
    filter_dismissed_from_dimensions,
    load_dismissed,
    recount_totals,
    restore_all_findings,
    restore_finding,
)


def _seed_projected_run(
    project_dir: Path,
    run_id: str,
    *,
    req: str,
    file: str,
    line: int,
    reason: str = "r",
) -> Path:
    """Create a run with one violation finding projected into evaluation.db."""
    run_dir = project_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log = run_dir / "events.jsonl"
    EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Security",
        file=file, line=line, reason=reason, req=req,
    )))
    Projector().project(log, run_dir)
    return run_dir


def _apply_actions(project_dir: Path, run_dir: Path) -> None:
    """Re-project actions log into the given run dir."""
    Projector().ensure_projected(
        run_dir / "events.jsonl", run_dir, project_dir=project_dir,
    )


class TestRestoreAllFindings:
    def test_restore_all_returns_count(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        r1 = _seed_projected_run(project_dir, "r1", req="A", file="a.py", line=1)
        r2 = _seed_projected_run(project_dir, "r2", req="B", file="b.py", line=2)
        dismiss_finding(project_dir, {"req": "A", "file": "a.py", "line": 1})
        dismiss_finding(project_dir, {"req": "B", "file": "b.py", "line": 2})
        _apply_actions(project_dir, r1)
        _apply_actions(project_dir, r2)
        count = restore_all_findings(project_dir)
        assert count == 2

    def test_restore_all_empty_returns_zero(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        assert restore_all_findings(project_dir) == 0

    def test_restore_single_does_not_write_dismissed_json(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        dismiss_finding(project_dir, {"req": "A", "file": "a.py", "line": 1})
        restore_finding(project_dir, {"req": "A", "file": "a.py", "line": 1})
        assert not (project_dir / "dismissed.json").exists()


class TestLoadDismissedEdgeCases:
    def test_load_returns_empty_when_no_runs(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        result = load_dismissed(project_dir)
        assert result == []


class TestCollectDismissedDetails:
    """Detail lookup walks runs newest-first and narrows each run's query."""

    @staticmethod
    def _started(run_dir: Path, started_at: str) -> None:
        (run_dir / "status.json").write_text(
            json.dumps({"started_at": started_at}), encoding="utf-8",
        )

    def test_newest_run_wins_when_several_know_the_key(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        old = _seed_projected_run(project_dir, "old", req="A", file="a.py", line=1, reason="old")
        new = _seed_projected_run(project_dir, "new", req="A", file="a.py", line=1, reason="new")
        self._started(old, "2026-01-01T00:00:00")
        self._started(new, "2026-02-01T00:00:00")
        dismiss_finding(project_dir, {"req": "A", "file": "a.py", "line": 1})

        (item,) = load_dismissed(project_dir)

        assert item["reason"] == "new"

    def test_each_run_is_asked_only_for_still_missing_keys(self, tmp_path, monkeypatch):
        from quodeq.services import dismissed as mod

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _seed_projected_run(project_dir, "r1", req="A", file="a.py", line=1)
        _seed_projected_run(project_dir, "r2", req="B", file="b.py", line=2)
        (project_dir / "empty").mkdir()  # no DB and no evaluation/: never queried
        dismiss_finding(project_dir, {"req": "A", "file": "a.py", "line": 1})
        dismiss_finding(project_dir, {"req": "B", "file": "b.py", "line": 2})
        seen: list[tuple[str, int]] = []
        real = mod.read_finding_details

        def spy(run_dir, keys):
            seen.append((run_dir.name, len(keys)))
            return real(run_dir, keys)

        monkeypatch.setattr(mod, "read_finding_details", spy)

        items = load_dismissed(project_dir)

        assert {i["req"] for i in items} == {"A", "B"}
        assert "empty" not in {name for name, _ in seen}
        assert [n for _, n in seen] == [2, 1]  # the second run only gets the leftover key

    def test_non_dict_status_json_does_not_break_the_listing(self, tmp_path):
        """status.json is parsed unchecked. A valid-JSON list must not turn
        the dismissed listing into a 500; the run just loses its
        started_at ordering and falls back to mtime."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        run = _seed_projected_run(project_dir, "r1", req="A", file="a.py", line=1, reason="only")
        (run / "status.json").write_text("[]", encoding="utf-8")
        dismiss_finding(project_dir, {"req": "A", "file": "a.py", "line": 1})

        (item,) = load_dismissed(project_dir)

        assert item["reason"] == "only"

    def test_started_at_is_read_once_per_run_across_requests(self, tmp_path, monkeypatch):
        """started_at never changes once written, so the listing must not
        re-parse every run's status.json on each request. A run without one
        yet is re-read, so it is ordered correctly once the scan writes it."""
        from quodeq.services import _run_recency as mod

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        stamped = _seed_projected_run(project_dir, "stamped", req="A", file="a.py", line=1)
        _seed_projected_run(project_dir, "pending", req="B", file="b.py", line=2)
        self._started(stamped, "2026-01-01T00:00:00")
        reads: list[str] = []
        real = mod.read_run_status_json

        def spy(run_dir):
            reads.append(run_dir.name)
            return real(run_dir)

        monkeypatch.setattr(mod, "read_run_status_json", spy)
        monkeypatch.setattr(mod, "_started_at_memo", {})

        mod.run_dirs_newest_first(project_dir)
        mod.run_dirs_newest_first(project_dir)

        assert reads.count("stamped") == 1
        assert reads.count("pending") == 2


class TestRecountTotals:
    def test_empty_list(self):
        totals = recount_totals([])
        assert totals.violation_count == 0
        assert totals.compliance_count == 0
        assert totals.severity.critical == 0

    def test_counts_severities(self):
        violations = [
            Finding(severity="critical"),
            Finding(severity="major"),
            Finding(severity="major"),
            Finding(severity="minor"),
            Finding(severity="unknown"),
        ]
        totals = recount_totals(violations, compliance_count=3)
        assert totals.violation_count == 5
        assert totals.compliance_count == 3
        assert totals.severity.critical == 1
        assert totals.severity.major == 2
        assert totals.severity.minor == 1
        assert totals.severity.unknown == 1

    def test_uses_old_totals_compliance(self):
        old = Totals(violation_count=10, compliance_count=7)
        totals = recount_totals([], old_totals=old)
        assert totals.compliance_count == 7

    def test_compliance_count_overrides_old(self):
        old = Totals(compliance_count=7)
        totals = recount_totals([], compliance_count=5, old_totals=old)
        assert totals.compliance_count == 5


@dataclass
class _FakeDimension:
    """Simulates DimensionResult for testing filter_dismissed_from_dimensions."""
    violations: list[Finding] = field(default_factory=list)
    totals: Totals = field(default_factory=Totals)


class TestFilterDismissedFromDimensions:
    def test_no_dismissed_returns_same(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        dim = _FakeDimension(violations=[Finding(req="A", file="a.py", line=1)])
        result = filter_dismissed_from_dimensions([dim], project_dir)
        assert len(result) == 1
        assert len(result[0].violations) == 1

    def test_filters_dismissed_findings(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        run_dir = _seed_projected_run(project_dir, "r1", req="A", file="a.py", line=1)
        dismiss_finding(project_dir, {"req": "A", "file": "a.py", "line": 1})
        _apply_actions(project_dir, run_dir)
        dim = _FakeDimension(
            violations=[
                Finding(req="A", file="a.py", line=1, severity="minor"),
                Finding(req="B", file="b.py", line=2, severity="major"),
            ],
            totals=Totals(violation_count=2, compliance_count=5),
        )
        result = filter_dismissed_from_dimensions([dim], project_dir)
        assert len(result[0].violations) == 1
        assert result[0].violations[0].req == "B"
        assert result[0].totals.violation_count == 1
