"""The dismissed listing resolves detail without walking every run.

Measured before this change on a project with 382 runs: an entry whose
finding no run held any more cost 5.9 s, on every open of the Dismissed
tab. The listing now asks the newest run, then the run the entry was
dismissed from, then the rest, and remembers the result while the actions
log and the run list are unchanged.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.data.events.writer import EventLogWriter
from quodeq.data.projection.projector import Projector
from quodeq.services.dismissed import dismiss_finding, dismissed_keys, load_dismissed
from quodeq.services.dismissed_listing import dismissed_item


def _seed_run(project_dir: Path, run_id: str, started_at: str, findings: list[tuple[str, str, int, str]]) -> Path:
    run_dir = project_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log = run_dir / "events.jsonl"
    writer = EventLogWriter(log)
    for req, file, line, reason in findings:
        writer.emit(JudgmentCreatedEvent(payload=JudgmentPayload(
            practice_id="P1", verdict="violation", dimension="Security",
            file=file, line=line, reason=reason, req=req,
        )))
    Projector().project(log, run_dir)
    (run_dir / "status.json").write_text(json.dumps({"started_at": started_at}), encoding="utf-8")
    return run_dir


@pytest.fixture()
def db_opens(monkeypatch):
    """Count evaluation.db connections made inside the test."""
    opened: list[str] = []
    real = sqlite3.connect

    def counting(database, *args, **kwargs):
        if str(database).endswith("evaluation.db"):
            opened.append(Path(str(database)).parent.name)
        return real(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", counting)
    return opened


def test_entry_in_the_newest_run_opens_that_run_only(tmp_path, db_opens):
    project_dir = tmp_path / "project"
    _seed_run(project_dir, "old", "2026-01-01T00:00:00", [("A", "a.py", 1, "old")])
    _seed_run(project_dir, "new", "2026-02-01T00:00:00", [("A", "a.py", 1, "new")])
    dismiss_finding(project_dir, {"req": "A", "file": "a.py", "line": 1}, run_id="old")
    dismissed_keys(project_dir)  # the one-shot fingerprint backfill, not the lookup
    db_opens.clear()

    (item,) = load_dismissed(project_dir)

    assert item["reason"] == "new"
    assert db_opens == ["new"]


def test_entry_gone_from_the_newest_run_is_read_from_its_recorded_run(tmp_path, db_opens):
    project_dir = tmp_path / "project"
    _seed_run(project_dir, "r1", "2026-01-01T00:00:00", [("A", "a.py", 1, "from r1")])
    _seed_run(project_dir, "r2", "2026-02-01T00:00:00", [("B", "b.py", 2, "unrelated")])
    _seed_run(project_dir, "r3", "2026-03-01T00:00:00", [("C", "c.py", 3, "unrelated")])
    dismiss_finding(project_dir, {"req": "A", "file": "a.py", "line": 1}, run_id="r1")
    dismissed_keys(project_dir)  # the one-shot fingerprint backfill, not the lookup
    db_opens.clear()

    (item,) = load_dismissed(project_dir)

    assert item["reason"] == "from r1"
    assert db_opens == ["r3", "r1"]


def test_legacy_entry_without_a_run_still_walks_to_its_detail(tmp_path, db_opens):
    project_dir = tmp_path / "project"
    _seed_run(project_dir, "r1", "2026-01-01T00:00:00", [("A", "a.py", 1, "from r1")])
    _seed_run(project_dir, "r2", "2026-02-01T00:00:00", [("B", "b.py", 2, "unrelated")])
    dismiss_finding(project_dir, {"req": "A", "file": "a.py", "line": 1})
    dismissed_keys(project_dir)  # the one-shot fingerprint backfill, not the lookup
    db_opens.clear()

    (item,) = load_dismissed(project_dir)

    assert item["reason"] == "from r1"
    assert db_opens == ["r2", "r1"]


def test_resolved_details_are_reused_until_the_actions_log_changes(tmp_path, db_opens):
    project_dir = tmp_path / "project"
    _seed_run(project_dir, "r1", "2026-01-01T00:00:00", [("A", "a.py", 1, "a"), ("B", "b.py", 2, "b")])
    dismiss_finding(project_dir, {"req": "A", "file": "a.py", "line": 1}, run_id="r1")
    load_dismissed(project_dir)
    db_opens.clear()

    load_dismissed(project_dir)
    assert db_opens == []

    dismiss_finding(project_dir, {"req": "B", "file": "b.py", "line": 2}, run_id="r1")
    db_opens.clear()
    items = load_dismissed(project_dir)
    assert {i["req"] for i in items} == {"A", "B"}
    assert db_opens == ["r1"]


def test_a_new_run_refreshes_the_resolved_details(tmp_path):
    project_dir = tmp_path / "project"
    _seed_run(project_dir, "r1", "2026-01-01T00:00:00", [("A", "a.py", 1, "old")])
    dismiss_finding(project_dir, {"req": "A", "file": "a.py", "line": 1}, run_id="r1")
    assert load_dismissed(project_dir)[0]["reason"] == "old"

    _seed_run(project_dir, "r2", "2026-02-01T00:00:00", [("A", "a.py", 1, "moved")])

    assert load_dismissed(project_dir)[0]["reason"] == "moved"


def test_dismissed_item_is_what_the_listing_shows(tmp_path):
    project_dir = tmp_path / "project"
    _seed_run(project_dir, "r1", "2026-01-01T00:00:00", [("A", "a.py", 1, "a")])
    dismiss_finding(project_dir, {"req": "A", "file": "a.py", "line": 1}, run_id="r1")

    item = dismissed_item(project_dir, "A", "a.py", 1)

    assert item == load_dismissed(project_dir)[0]
    assert item["reason"] == "a"
    assert dismissed_item(project_dir, "Z", "z.py", 9) is None
