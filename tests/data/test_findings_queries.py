"""Read-only findings-table queries live in the data layer, not in services.

dismissed.py, deleted.py and run_keys.py used to inline this SQL, coupling
service flows to the schema (and importing sqlite3 into the service layer).
The queries now live in ``data/sqlite/findings_queries.py``; services call
them and no longer carry any database dependency at runtime. This module
covers the detail/key-set/dismissed lookups; the snippet readers, active
findings stream and source stamp live in test_findings_queries_snippets.py.
"""
from __future__ import annotations

from quodeq.core.finding_identity import snippet_fingerprint
from quodeq.data.sqlite.state_store import SQLiteStateStore
from tests.data._findings_queries_helpers import _break_reopen_with_operational_error, _seed


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

    def test_fingerprint_key_finds_the_finding_at_any_line(self, tmp_path):
        """The Dismissed tab keeps showing a dismissed finding after it moved."""
        from quodeq.data.sqlite.findings_queries import read_finding_details

        _seed(tmp_path, req="X-1", file="src/a.py", line=42, snippet="x = 1")
        key = ("X-1", "src/a.py", snippet_fingerprint("X-1", "x = 1"))

        out = read_finding_details(tmp_path, {key, ("X-1", "src/a.py", 10)})

        assert set(out) == {key}
        assert out[key]["line"] == 42

    def test_fingerprint_key_ignores_different_code(self, tmp_path):
        from quodeq.data.sqlite.findings_queries import read_finding_details

        _seed(tmp_path, req="X-1", file="src/a.py", line=10, snippet="y = 2")
        key = ("X-1", "src/a.py", snippet_fingerprint("X-1", "x = 1"))

        assert read_finding_details(tmp_path, {key}) == {}

    def test_principle_keyed_dismissal_matches_a_requirement_less_finding(self, tmp_path):
        """The UI records a no-req finding under ``req || principle``."""
        from quodeq.data.sqlite.findings_queries import read_finding_details

        _seed(tmp_path, req=None, file="src/a.py", line=10, practice_id="Modularity")

        out = read_finding_details(tmp_path, {("Modularity", "src/a.py", 10)})

        assert set(out) == {("Modularity", "src/a.py", 10)}

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

        # Both identity shapes: the line key and the snippet fingerprint key.
        assert dismiss == {
            ("X-1", "src/a.py", 10),
            ("X-1", "src/a.py", snippet_fingerprint("X-1", "s")),
        }
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

        assert rows == [("X-1", "src/a.py", 10, "P1", "s")]

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
