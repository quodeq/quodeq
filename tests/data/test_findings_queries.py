"""Read-only findings-table queries live in the data layer, not in services.

dismissed.py, deleted.py and run_keys.py used to inline this SQL, coupling
service flows to the schema (and importing sqlite3 into the service layer).
The queries now live in ``data/sqlite/findings_queries.py``; services call
them and no longer carry any database dependency at runtime.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from quodeq.core.events.models import Judgment
from quodeq.data.sqlite.state_store import SQLiteStateStore


def _seed(run_dir: Path, **kw) -> None:
    defaults = dict(
        practice_id="P1", verdict="violation", dimension="clean-architecture",
        file="src/a.py", line=10, reason="r", req="X-1", severity="major",
        title="t", snippet="s",
    )
    SQLiteStateStore(run_dir).record_finding(Judgment(**{**defaults, **kw}))


def _break_reopen_with_operational_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """After this, the next open_evaluation_db() call raises RuntimeError
    (wrapping sqlite3.OperationalError), mirroring a locked/IO-erroring DB.
    Mirrors the technique in tests/data/sqlite/test_connection.py."""
    monkeypatch.setattr(
        "quodeq.data.sqlite.connection.apply_evaluation_schema",
        lambda conn: (_ for _ in ()).throw(sqlite3.OperationalError("disk I/O error")),
    )


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

    def test_locked_or_io_erroring_db_degrades_gracefully(self, tmp_path, monkeypatch):
        """open_evaluation_db wraps a locked/IO-erroring DB as RuntimeError
        (Task D10); the best-effort contract this docstring describes must
        still hold for that failure mode, not just sqlite3.DatabaseError."""
        from quodeq.data.sqlite.findings_queries import read_finding_details

        _seed(tmp_path, req="X-1", file="src/a.py", line=10)
        _break_reopen_with_operational_error(monkeypatch)

        assert read_finding_details(tmp_path, {("X-1", "src/a.py", 10)}) == {}

    def test_matches_requirement_less_findings_via_null_or_empty(self, tmp_path):
        """A finding with no requirement id is stored with requirement NULL;
        callers key it as "" (see services/dismissed.py's key-building), so
        the lookup must match NULL rows on an empty-requirement key without
        also picking up an unrelated req-bearing finding at the same key."""
        from quodeq.data.sqlite.findings_queries import read_finding_details

        _seed(tmp_path, req=None, file="src/a.py", line=10)
        _seed(tmp_path, req="X-2", file="src/b.py", line=20, practice_id="P2")

        out = read_finding_details(
            tmp_path, {("", "src/a.py", 10), ("X-2", "src/b.py", 20)},
        )

        assert set(out) == {("", "src/a.py", 10), ("X-2", "src/b.py", 20)}
        assert out[("", "src/a.py", 10)]["req"] == ""

    def test_chunking_across_multiple_batches_drops_nothing_and_dedupes(self, tmp_path):
        """Regression for the SQL-side rewrite: keys are split into chunks to
        stay under SQLite's ~999 bind-parameter limit. 350 keys forces 2+
        chunks at the 300-per-batch size; every key must still come back
        exactly once."""
        from quodeq.data.sqlite.findings_queries import read_finding_details

        total = 350
        keys: set[tuple] = set()
        for i in range(total):
            req, file, line = f"REQ-{i}", f"src/f{i}.py", i + 1
            _seed(tmp_path, req=req, file=file, line=line, practice_id="P1")
            keys.add((req, file, line))

        out = read_finding_details(tmp_path, keys)

        assert set(out) == keys
        assert len(out) == total
        assert out[("REQ-0", "src/f0.py", 1)]["req"] == "REQ-0"
        assert out[("REQ-349", "src/f349.py", 350)]["req"] == "REQ-349"


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

    def test_locked_or_io_erroring_db_degrades_gracefully(self, tmp_path, monkeypatch):
        from quodeq.data.sqlite.findings_queries import read_run_key_sets

        _seed(tmp_path)
        _break_reopen_with_operational_error(monkeypatch)

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

    def test_locked_or_io_erroring_db_degrades_gracefully(self, tmp_path, monkeypatch):
        from quodeq.data.sqlite.findings_queries import find_dismissed_matching

        _seed(tmp_path, req="X-1", file="src/a.py", line=10)
        store = SQLiteStateStore(tmp_path)
        store.update_verdict(req="X-1", file="src/a.py", line=10, verdict="dismissed")
        _break_reopen_with_operational_error(monkeypatch)

        assert find_dismissed_matching(
            tmp_path, dimension="clean-architecture", practice_id="P1", file="src/a.py",
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


class TestDismissedSnippetReaders:
    """Precedent matching (context/precedent.py) used to inline these SELECTs."""

    def test_read_dismissed_snippets_returns_pairs(self, tmp_path):
        from quodeq.data.sqlite.findings_queries import read_dismissed_snippets

        _seed(tmp_path, req="X-1", file="src/a.py", line=10, snippet="bad()")
        _seed(tmp_path, req="X-2", file="src/b.py", line=20, practice_id="P2")
        store = SQLiteStateStore(tmp_path)
        store.update_verdict(req="X-1", file="src/a.py", line=10, verdict="dismissed")

        assert read_dismissed_snippets(tmp_path) == [("X-1", "bad()")]

    def test_read_dismissed_snippets_missing_db(self, tmp_path):
        from quodeq.data.sqlite.findings_queries import read_dismissed_snippets

        assert read_dismissed_snippets(tmp_path) == []

    def test_semantic_eligible_excludes_scoped_and_empty(self, tmp_path):
        from quodeq.data.sqlite.findings_queries import read_semantic_eligible_dismissals

        # eligible: line > 0, non-empty snippet, no scope
        _seed(tmp_path, req="OK-1", file="a.py", line=5, snippet="real()")
        # excluded: empty snippet
        _seed(tmp_path, req="NO-1", file="b.py", line=5, snippet="   ", practice_id="P2")
        # excluded: scope-level finding
        _seed(tmp_path, req="NO-2", file="c.py", line=5, snippet="x()", scope="module", practice_id="P3")
        store = SQLiteStateStore(tmp_path)
        for req, f in [("OK-1", "a.py"), ("NO-1", "b.py"), ("NO-2", "c.py")]:
            store.update_verdict(req=req, file=f, line=5, verdict="dismissed")

        assert read_semantic_eligible_dismissals(tmp_path) == [("OK-1", "real()")]

    def test_semantic_eligible_missing_db(self, tmp_path):
        from quodeq.data.sqlite.findings_queries import read_semantic_eligible_dismissals

        assert read_semantic_eligible_dismissals(tmp_path) == []


class TestReadActiveFindings:
    """The scores response builder (services.scoring) used to inline this SELECT."""

    def test_returns_only_non_dismissed_rows_in_id_order(self, tmp_path):
        from quodeq.data.sqlite.findings_queries import read_active_findings

        _seed(tmp_path, req="X-1", file="src/a.py", line=10)
        _seed(tmp_path, req="X-2", file="src/b.py", line=20, practice_id="P2",
              verdict="compliance")
        _seed(tmp_path, req="X-3", file="src/c.py", line=30, practice_id="P3")
        store = SQLiteStateStore(tmp_path)
        store.update_verdict(req="X-3", file="src/c.py", line=30, verdict="dismissed")

        rows = read_active_findings(tmp_path)

        assert [r["requirement"] for r in rows] == ["X-1", "X-2"]
        assert [r["verdict"] for r in rows] == ["violation", "compliance"]

    def test_row_shape_matches_row_to_finding_contract(self, tmp_path):
        from quodeq.data.sqlite._row_mappers import row_to_finding
        from quodeq.data.sqlite.findings_queries import read_active_findings

        _seed(tmp_path)
        (row,) = read_active_findings(tmp_path)

        assert {
            "id", "practice_id", "dimension", "requirement", "verdict",
            "severity", "file", "line", "end_line", "title", "reason",
            "snippet", "violation_type", "context", "scope", "req_refs_json",
            "confidence", "provenance_downgrade", "scope_downgrade_json",
        } <= set(row)
        f = row_to_finding(row)
        assert (f.req, f.file, f.line) == ("X-1", "src/a.py", 10)
        assert f.dimension == "clean-architecture"

    def test_empty_db_returns_no_rows(self, tmp_path):
        from quodeq.data.sqlite.findings_queries import read_active_findings

        assert read_active_findings(tmp_path) == []


def test_precedent_carries_no_database_dependency():
    """context/precedent.py must not import the sqlite connection helper."""
    import quodeq.context.precedent as precedent

    src = open(precedent.__file__).read()
    assert "open_evaluation_db" not in src
    assert "FROM findings" not in src
