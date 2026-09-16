"""A dismissal survives the line shift every refactor causes (issue #1165).

Run r1 flags a snippet at line 10; the user dismisses it there. Run r2 holds
the same code at line 22. The dismissal must hide the finding in r2 on every
surface -- the services read side, the SQL projection, the Dismissed tab --
and restoring it from the tab must release it everywhere. Legacy entries
written before fingerprints existed are upgraded once by the backfill.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.finding_identity import snippet_fingerprint
from quodeq.core.types.finding import Finding
from quodeq.data.events.writer import EventLogWriter
from quodeq.data.projection.projector import Projector
from quodeq.data.sqlite.connection import open_evaluation_db
from quodeq.services._dismiss_fingerprints import BACKFILL_MARKER, backfill_if_needed
from quodeq.services.deleted import delete_finding
from quodeq.services._dismissed_listing import load_dismissed
from quodeq.services.dismissed import (
    dismiss_finding,
    dismissed_keys,
    restore_all_findings,
    restore_finding,
)
from quodeq.services.suppression import is_dismissed

SNIP = "except Exception:\n    pass"
FP = snippet_fingerprint("R1", SNIP)


def _seed_run(
    project_dir: Path, run_id: str, *, line: int, snippet: str | None = SNIP,
    req: str | None = "R1", started_at: str | None = None,
) -> Path:
    run_dir = project_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    EventLogWriter(run_dir / "events.jsonl").emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Reliability",
        file="a.py", line=line, reason="r", req=req, snippet=snippet or None,
    )))
    if started_at:
        (run_dir / "status.json").write_text(json.dumps({"started_at": started_at}), encoding="utf-8")
    _project(project_dir, run_dir)
    return run_dir


def _project(project_dir: Path, run_dir: Path) -> None:
    Projector().ensure_projected(run_dir / "events.jsonl", run_dir, project_dir=project_dir)


def _verdict(run_dir: Path, line: int) -> str:
    with open_evaluation_db(run_dir) as conn:
        return conn.execute(
            "SELECT verdict FROM findings WHERE file='a.py' AND line=?", (line,)).fetchone()[0]


def _finding(line: int, snippet: str | None = SNIP) -> Finding:
    return Finding(req="R1", practice_id="P1", file="a.py", line=line, snippet=snippet)


def test_dismiss_records_the_fingerprint_of_the_stored_snippet(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    _seed_run(project_dir, "r1", line=10)

    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10}, run_id="r1")

    (entry,) = dismissed_keys(project_dir).entries
    assert entry.fingerprint == FP
    assert entry.line == 10


def test_client_snippet_is_the_fallback_when_no_run_holds_the_finding(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"

    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10, "snippet": SNIP})

    (entry,) = dismissed_keys(project_dir).entries
    assert entry.fingerprint == FP


def test_snippet_less_finding_keeps_its_line_identity(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    _seed_run(project_dir, "r1", line=10, snippet=None)

    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10}, run_id="r1")

    state = dismissed_keys(project_dir)
    assert state.entries[0].fingerprint is None
    assert is_dismissed(state, req="R1", file="a.py", line=10)
    assert not is_dismissed(state, req="R1", file="a.py", line=11)


def test_dismissal_follows_the_finding_to_its_new_line(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    r1 = _seed_run(project_dir, "r1", line=10)
    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10}, run_id="r1")
    _project(project_dir, r1)

    r2 = _seed_run(project_dir, "r2", line=22)

    state = dismissed_keys(project_dir)
    assert is_dismissed(state, req="R1", file="a.py", line=22, snippet=SNIP)
    assert _verdict(r1, 10) == "dismissed"
    assert _verdict(r2, 22) == "dismissed"


def test_different_code_at_the_old_line_is_not_hidden(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    _seed_run(project_dir, "r1", line=10)
    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10}, run_id="r1")

    r2 = _seed_run(project_dir, "r2", line=10, snippet="return cache[key]")

    state = dismissed_keys(project_dir)
    assert not is_dismissed(state, req="R1", file="a.py", line=10, snippet="return cache[key]")
    assert _verdict(r2, 10) == "violation"


def test_listing_shows_the_current_line_and_the_fingerprint(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    _seed_run(project_dir, "r1", line=10, started_at="2026-01-01T00:00:00+00:00")
    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10}, run_id="r1")
    _seed_run(project_dir, "r2", line=22, started_at="2026-02-01T00:00:00+00:00")

    (item,) = load_dismissed(project_dir)

    assert item["fingerprint"] == FP
    assert item["line"] == 22          # newest run's location
    assert item["snippet"] == SNIP
    assert item["req"] == "R1"


def test_restore_by_fingerprint_releases_the_moved_finding_everywhere(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    r1 = _seed_run(project_dir, "r1", line=10)
    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10}, run_id="r1")
    r2 = _seed_run(project_dir, "r2", line=22)
    (item,) = load_dismissed(project_dir)

    # The tab sends the current line (22) plus the fingerprint.
    restore_finding(project_dir, {"req": item["req"], "file": item["file"],
                                  "line": item["line"], "fingerprint": item["fingerprint"]})
    _project(project_dir, r1)
    _project(project_dir, r2)

    assert not dismissed_keys(project_dir)
    assert _verdict(r1, 10) == "violation"
    assert _verdict(r2, 22) == "violation"


def test_restore_without_fingerprint_resolves_the_entry_at_the_recorded_line(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    _seed_run(project_dir, "r1", line=10)
    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10}, run_id="r1")

    restore_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10})

    assert not dismissed_keys(project_dir)
    text = (project_dir / "actions.jsonl").read_text()
    assert text.count(FP) == 2  # the dismiss and the undismiss both name it


def test_restore_without_fingerprint_at_the_new_line_fingerprints_the_finding(tmp_path: Path) -> None:
    """An older client names the moved finding by its new line only."""
    project_dir = tmp_path / "proj"
    _seed_run(project_dir, "r1", line=10)
    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10}, run_id="r1")
    _seed_run(project_dir, "r2", line=22)

    restore_finding(project_dir, {"req": "R1", "file": "a.py", "line": 22})

    assert not dismissed_keys(project_dir)


def test_restore_all_names_every_entry_by_fingerprint(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    _seed_run(project_dir, "r1", line=10)
    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10}, run_id="r1")
    _seed_run(project_dir, "r2", line=22)

    assert restore_all_findings(project_dir) == 1
    assert not dismissed_keys(project_dir)


def test_delete_sweep_releases_the_dismissal_from_a_run_where_it_moved(tmp_path: Path) -> None:
    project_dir = tmp_path / "proj"
    _seed_run(project_dir, "r1", line=10)
    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10}, run_id="r1")
    _seed_run(project_dir, "r2", line=22)  # projected: dismissed at line 22

    swept = delete_finding(project_dir, {"dimension": "Reliability", "principle": "P1", "file": "a.py"})

    assert swept >= 1
    assert not dismissed_keys(project_dir)


class TestBackfill:
    def _legacy_dismiss(self, project_dir: Path, *, line: int, when: datetime) -> None:
        """A pre-fingerprint actions.jsonl line, as older releases wrote it."""
        project_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "event_id": "0f9d1e5e-3d1b-4c9a-9f5a-000000000001",
            "timestamp": when.isoformat().replace("+00:00", "Z"),
            "event_type": "FINDING_DISMISSED",
            "payload": {"req": "R1", "file": "a.py", "line": line, "reason": "legacy"},
        }
        with open(project_dir / "actions.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def test_legacy_entry_is_upgraded_and_follows_the_finding(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "proj"
        _seed_run(project_dir, "r1", line=10, started_at="2026-01-01T00:00:00+00:00")
        self._legacy_dismiss(project_dir, line=10, when=datetime(2026, 1, 2, tzinfo=timezone.utc))
        r2 = _seed_run(project_dir, "r2", line=22, started_at="2026-03-01T00:00:00+00:00")

        state = dismissed_keys(project_dir)

        (entry,) = state.entries
        assert entry.fingerprint == FP
        assert entry.reason == "legacy"
        assert is_dismissed(state, req="R1", file="a.py", line=22, snippet=SNIP)
        _project(project_dir, r2)
        assert _verdict(r2, 22) == "dismissed"
        assert (project_dir / BACKFILL_MARKER).exists()

    def test_backfill_prefers_the_run_the_user_was_looking_at(self, tmp_path: Path) -> None:
        """A later run holds different code at the same line; the dismissal
        was recorded against what the earlier run showed."""
        project_dir = tmp_path / "proj"
        _seed_run(project_dir, "r1", line=10, started_at="2026-01-01T00:00:00+00:00")
        when = datetime(2026, 1, 2, tzinfo=timezone.utc)
        self._legacy_dismiss(project_dir, line=10, when=when)
        r2 = _seed_run(project_dir, "r2", line=10, snippet="return cache[key]",
                       started_at=(when + timedelta(days=30)).isoformat())
        assert _verdict(r2, 10) == "dismissed"  # the line key still hid the wrong code

        (entry,) = dismissed_keys(project_dir).entries

        assert entry.fingerprint == FP
        # The upgraded entry supersedes the line key: re-projecting r2 releases
        # the different code that the legacy line match had hidden.
        _project(project_dir, r2)
        assert _verdict(r2, 10) == "violation"

    def test_unresolvable_entry_stays_line_keyed_and_runs_once(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "proj"
        self._legacy_dismiss(project_dir, line=10, when=datetime(2026, 1, 2, tzinfo=timezone.utc))

        assert backfill_if_needed(project_dir) == 0
        (entry,) = dismissed_keys(project_dir).entries
        assert entry.fingerprint is None
        assert (project_dir / BACKFILL_MARKER).exists()
        # A run appearing later does not re-run the one-shot backfill.
        _seed_run(project_dir, "r1", line=10)
        assert backfill_if_needed(project_dir) == 0

    def test_restored_legacy_entry_is_not_resurrected(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "proj"
        _seed_run(project_dir, "r1", line=10)
        self._legacy_dismiss(project_dir, line=10, when=datetime(2026, 1, 2, tzinfo=timezone.utc))
        restore_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10})

        assert not dismissed_keys(project_dir)
        assert backfill_if_needed(project_dir) == 0

    def test_project_without_a_log_writes_no_marker(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        assert backfill_if_needed(project_dir) == 0
        assert not (project_dir / BACKFILL_MARKER).exists()

    def test_shared_results_clone_is_never_written(self, tmp_path: Path) -> None:
        """A mirror is refreshed by fetch + hard reset; its log is the publisher's."""
        clone = tmp_path / "clone"
        (clone / ".git").mkdir(parents=True)
        (clone / "quodeq.json").write_text("{}", encoding="utf-8")
        project_dir = clone / "evaluations" / "proj"
        _seed_run(project_dir, "r1", line=10)
        self._legacy_dismiss(project_dir, line=10, when=datetime(2026, 1, 2, tzinfo=timezone.utc))
        before = (project_dir / "actions.jsonl").read_text()

        assert backfill_if_needed(project_dir) == 0
        (entry,) = dismissed_keys(project_dir).entries

        assert entry.fingerprint is None
        assert (project_dir / "actions.jsonl").read_text() == before
        assert not (project_dir / BACKFILL_MARKER).exists()
