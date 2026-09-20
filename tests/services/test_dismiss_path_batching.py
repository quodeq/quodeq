"""The dismiss/delete path appends its undismiss events in batches.

Restoring all dismissals, converting them to permanent suppressions and
sweeping a deletion across runs used to open, lock and flush ``actions.jsonl``
once per row. Each operation now hands the writer one batch: per operation
for restore-all and delete-all, per run for the delete sweep, which keeps the
sweep's memory bounded to one run's matches. The Dismissed tab listing only
looks up finding detail for the page it was asked for.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.events.models import (
    BaseEvent,
    FindingUndismissedEvent,
    JudgmentCreatedEvent,
    JudgmentPayload,
)
from quodeq.data.events.writer import EventLogWriter
from quodeq.data.projection.projector import Projector
from quodeq.services import dismissed_listing as listing_mod
from quodeq.services.dismissed_listing import load_dismissed
from quodeq.services.deleted import _sweep_dismissed_matching, delete_all_dismissed
from quodeq.services.dismissed import dismiss_finding, restore_all_findings

DIMENSION = "maintainability"
PRINCIPLE = "Modularity"


class _BatchLog:
    """Records every append the services make, one entry per writer call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[BaseEvent]]] = []

    def emit(self, event: BaseEvent) -> None:
        self.calls.append(("emit", [event]))

    def emit_many(self, events) -> None:
        self.calls.append(("emit_many", list(events)))

    def kinds(self) -> list[str]:
        return [kind for kind, _ in self.calls]

    def undismissed_reqs(self) -> list[str]:
        return sorted(event.payload.req for _, batch in self.calls for event in batch)


def _finding(req: str, file: str, line: int) -> dict:
    return {"req": req, "file": file, "line": line, "dimension": DIMENSION, "principle": PRINCIPLE}


def _seed_run(
    project_dir: Path, run_id: str, findings: list[dict], *, started_at: str | None = None,
) -> Path:
    """One projected run holding *findings*, each with its own snippet."""
    run_dir = project_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if started_at:
        (run_dir / "status.json").write_text(json.dumps({"started_at": started_at}), encoding="utf-8")
    log = EventLogWriter(run_dir / "events.jsonl")
    for finding in findings:
        log.emit(JudgmentCreatedEvent(payload=JudgmentPayload(
            practice_id=PRINCIPLE, verdict="violation", dimension=DIMENSION,
            file=finding["file"], line=finding["line"], reason="r", req=finding["req"],
            snippet=f"code at {finding['file']}:{finding['line']}",
        )))
    Projector().project(run_dir / "events.jsonl", run_dir)
    return run_dir


def _dismiss_and_project(project_dir: Path, findings: list[dict], *runs: Path) -> None:
    for finding in findings:
        dismiss_finding(project_dir, finding)
    for run_dir in runs:
        Projector().ensure_projected(run_dir / "events.jsonl", run_dir, project_dir=project_dir)


def test_restore_all_appends_every_undismiss_in_one_batch(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    findings = [_finding("R1", "a.py", 1), _finding("R2", "b.py", 2), _finding("R3", "c.py", 3)]
    _seed_run(project_dir, "r1", findings)
    _dismiss_and_project(project_dir, findings)
    log = _BatchLog()

    count = restore_all_findings(project_dir, writer=log)

    assert count == 3
    assert log.kinds() == ["emit_many"]
    assert log.undismissed_reqs() == ["R1", "R2", "R3"]
    assert all(isinstance(e, FindingUndismissedEvent) for _, batch in log.calls for e in batch)


def test_delete_all_dismissed_appends_every_undismiss_in_one_batch(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    findings = [_finding("R1", "a.py", 1), _finding("R2", "b.py", 2)]
    run = _seed_run(project_dir, "r1", findings)
    _dismiss_and_project(project_dir, findings, run)
    log = _BatchLog()

    count = delete_all_dismissed(project_dir, writer=log)

    assert count == 2
    assert log.kinds() == ["emit_many"]
    assert log.undismissed_reqs() == ["R1", "R2"]


def test_delete_sweep_appends_one_batch_per_run_and_releases_each_entry_once(
    tmp_path: Path,
) -> None:
    """Runs are swept newest first. An entry two runs hold is released by the
    first run's batch only; the log grows by entries, not by rows."""
    project_dir = tmp_path / "proj"
    shared = [_finding("R1", "a.py", 1), _finding("R2", "a.py", 2)]
    only_old = [_finding("R4", "a.py", 4)]
    miss = [_finding("R3", "other.py", 3)]
    newest = _seed_run(project_dir, "run-new", shared, started_at="2026-02-01T00:00:00+00:00")
    older = _seed_run(project_dir, "run-old", shared + only_old, started_at="2026-01-01T00:00:00+00:00")
    other = _seed_run(project_dir, "run-other", miss, started_at="2026-01-15T00:00:00+00:00")
    _dismiss_and_project(project_dir, shared + only_old + miss, newest, older, other)
    log = _BatchLog()

    count = _sweep_dismissed_matching(project_dir, (DIMENSION, PRINCIPLE, "a.py"), writer=log)

    assert count == 3
    assert log.kinds() == ["emit_many", "emit_many"]
    assert [sorted(e.payload.req for e in batch) for _, batch in log.calls] == [["R1", "R2"], ["R4"]]


def _spy_detail_reads(monkeypatch) -> list[set]:
    """Every key set the listing asks a run's findings table for."""
    seen: list[set] = []
    real = listing_mod.read_finding_details

    def spy(run_dir, keys):
        seen.append(set(keys))
        return real(run_dir, keys)

    monkeypatch.setattr(listing_mod, "read_finding_details", spy)
    return seen


def test_dismissed_listing_page_only_looks_up_the_entries_on_the_page(
    tmp_path: Path, monkeypatch,
) -> None:
    project_dir = tmp_path / "proj"
    findings = [_finding(f"R{i}", "a.py", i) for i in range(1, 6)]
    _seed_run(project_dir, "r1", findings)
    _dismiss_and_project(project_dir, findings)
    everything = load_dismissed(project_dir)
    seen = _spy_detail_reads(monkeypatch)

    page = load_dismissed(project_dir, offset=1, limit=2)

    assert page == everything[1:3]
    assert set().union(*seen) == {(item["req"], item["file"], item["fingerprint"]) for item in page}


def test_dismissed_listing_page_past_the_end_reads_no_run(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "proj"
    findings = [_finding("R1", "a.py", 1)]
    _seed_run(project_dir, "r1", findings)
    _dismiss_and_project(project_dir, findings)
    seen = _spy_detail_reads(monkeypatch)

    assert load_dismissed(project_dir, offset=5, limit=2) == []
    assert seen == []
