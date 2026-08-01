"""Read-only findings-table queries live in the data layer, not in services.

dismissed.py, deleted.py and run_keys.py used to inline this SQL, coupling
service flows to the schema (and importing sqlite3 into the service layer).
The queries now live in ``data/sqlite/findings_queries.py``; services call
them and no longer carry any database dependency at runtime.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.events.models import Judgment
from quodeq.data.sqlite.state_store import SQLiteStateStore


def _seed(run_dir: Path, **kw) -> None:
    defaults = dict(
        practice_id="P1", verdict="violation", dimension="clean-architecture",
        file="src/a.py", line=10, reason="r", req="X-1", severity="major",
        title="t", snippet="s",
    )
    SQLiteStateStore(run_dir).record_finding(Judgment(**{**defaults, **kw}))


class TestReadFindingDetails:
    def test_returns_details_for_matching_keys_only(self, tmp_path):
        from quodeq.data.sqlite.findings_queries import read_finding_details

        _seed(tmp_path, req="X-1", file="src/a.py", line=10)
        _seed(tmp_path, req="X-2", file="src/b.py", line=20, practice_id="P2")

        out = read_finding_details(tmp_path, {("X-1", "src/a.py", 10)})

        assert set(out) == {("X-1", "src/a.py", 10)}
        detail = out[("X-1", "src/a.py", 10)]
        assert detail["req"] == "X-1"
        assert detail["principle"] == "P1"
        assert detail["severity"] == "major"

    def test_missing_db_returns_empty(self, tmp_path):
        from quodeq.data.sqlite.findings_queries import read_finding_details

        assert read_finding_details(tmp_path, {("X", "f", 1)}) == {}


class TestReadRunKeySets:
    def test_returns_dismiss_and_class_keys(self, tmp_path):
        from quodeq.data.sqlite.findings_queries import read_run_key_sets

        _seed(tmp_path)
        dismiss, cls = read_run_key_sets(tmp_path)

        assert dismiss == {("X-1", "src/a.py", 10)}
        assert cls == {("clean-architecture", "P1", "src/a.py")}

    def test_missing_db_returns_empty_sets(self, tmp_path):
        from quodeq.data.sqlite.findings_queries import read_run_key_sets

        assert read_run_key_sets(tmp_path) == (set(), set())


class TestFindDismissedMatching:
    def test_returns_only_dismissed_rows_matching_key(self, tmp_path):
        from quodeq.data.sqlite.findings_queries import find_dismissed_matching

        _seed(tmp_path, req="X-1", file="src/a.py", line=10)
        _seed(tmp_path, req="X-2", file="src/a.py", line=30, practice_id="P2")
        store = SQLiteStateStore(tmp_path)
        store.update_verdict(req="X-1", file="src/a.py", line=10, verdict="dismissed")

        rows = find_dismissed_matching(
            tmp_path, dimension="clean-architecture", practice_id="P1", file="src/a.py",
        )

        assert rows == [("X-1", "src/a.py", 10)]

    def test_missing_db_returns_empty(self, tmp_path):
        from quodeq.data.sqlite.findings_queries import find_dismissed_matching

        assert find_dismissed_matching(
            tmp_path, dimension="d", practice_id="p", file="f",
        ) == []


def test_services_carry_no_database_dependency():
    """The service modules must not import sqlite3 or the connection helper
    at runtime — the schema is an adapter-layer detail now."""
    import quodeq.services.deleted as deleted
    import quodeq.services.dismissed as dismissed
    import quodeq.services.run_keys as run_keys

    for mod in (dismissed, deleted, run_keys):
        assert "sqlite3" not in vars(mod), mod.__name__
        assert "open_evaluation_db" not in vars(mod), mod.__name__
