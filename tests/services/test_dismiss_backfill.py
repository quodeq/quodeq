"""Legacy line-keyed dismissals are upgraded to fingerprints once (issue #1165).

Entries written before fingerprints existed carry only (req, file, line).
The first read after the upgrade appends a fingerprinted event for each one
whose snippet a run still holds, preferring the run the user was looking at
when they dismissed. Shared mirrors are never written.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from quodeq.core.finding_identity import snippet_fingerprint
from quodeq.services import _dismiss_fingerprints as fingerprints_mod
from quodeq.services._dismiss_fingerprints import BACKFILL_MARKER, _backfill_locks, backfill_if_needed
from quodeq.services.dismissed import dismissed_keys, restore_finding
from quodeq.services.suppression import is_dismissed
from tests.services.test_dismissed_fingerprint import FP, SNIP, _project, _seed_run, _verdict


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

    def test_lock_entry_is_evicted_once_the_project_is_done(self, tmp_path: Path) -> None:
        """Only in-flight projects hold a lock: a dashboard listing many
        projects must not keep one per project for the life of the process."""
        project_dir = tmp_path / "proj"
        _seed_run(project_dir, "r1", line=10)
        self._legacy_dismiss(project_dir, line=10, when=datetime(2026, 1, 2, tzinfo=timezone.utc))

        assert backfill_if_needed(project_dir) == 1
        assert not _backfill_locks
        assert backfill_if_needed(project_dir) == 0  # marker short-circuit
        assert not _backfill_locks

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

    def test_backfill_reads_each_run_once_for_all_pending_entries(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        """Three legacy entries, three runs: one detail read and at most one
        status read per run, not one per entry per run."""
        project_dir = tmp_path / "proj"
        _seed_run(project_dir, "r1", line=10, started_at="2026-01-01T00:00:00+00:00")
        _seed_run(project_dir, "r1", line=30, snippet="return cache[key]")
        when = datetime(2026, 1, 2, tzinfo=timezone.utc)
        for line in (10, 30, 50):
            self._legacy_dismiss(project_dir, line=line, when=when)
        _seed_run(project_dir, "r2", line=10, started_at="2026-03-01T00:00:00+00:00")
        _seed_run(project_dir, "r3", line=10, started_at="2026-04-01T00:00:00+00:00")
        detail_reads = _count_calls_per_run(monkeypatch, "read_finding_details")
        status_reads = _count_calls_per_run(monkeypatch, "read_run_status_json")

        assert backfill_if_needed(project_dir) == 2

        assert max(detail_reads.values()) == 1
        assert max(status_reads.values(), default=0) <= 1
        fingerprints = {e.line: e.fingerprint for e in dismissed_keys(project_dir).entries}
        assert fingerprints == {
            10: FP, 30: snippet_fingerprint("R1", "return cache[key]"), 50: None,
        }

    def test_backfill_keeps_each_entry_s_own_run_preference(self, tmp_path: Path) -> None:
        """One entry's code exists only in a run started after the dismissal;
        the other's line holds different code there. Each resolves from the
        run that showed what the user dismissed."""
        project_dir = tmp_path / "proj"
        _seed_run(project_dir, "r1", line=10, started_at="2026-01-01T00:00:00+00:00")
        when = datetime(2026, 1, 2, tzinfo=timezone.utc)
        self._legacy_dismiss(project_dir, line=10, when=when)
        self._legacy_dismiss(project_dir, line=40, when=when)
        _seed_run(project_dir, "r2", line=10, snippet="return cache[key]",
                  started_at="2026-03-01T00:00:00+00:00")
        _seed_run(project_dir, "r2", line=40, snippet="del cache[key]")

        assert backfill_if_needed(project_dir) == 2

        fingerprints = {e.line: e.fingerprint for e in dismissed_keys(project_dir).entries}
        assert fingerprints == {10: FP, 40: snippet_fingerprint("R1", "del cache[key]")}


def _count_calls_per_run(monkeypatch, name: str) -> dict[Path, int]:
    """Count the calls the backfill makes to the run reader *name*, per run."""
    counts: dict[Path, int] = {}
    real = getattr(fingerprints_mod, name)

    def spy(run_dir, *args, **kwargs):
        counts[run_dir] = counts.get(run_dir, 0) + 1
        return real(run_dir, *args, **kwargs)

    monkeypatch.setattr(fingerprints_mod, name, spy)
    return counts
