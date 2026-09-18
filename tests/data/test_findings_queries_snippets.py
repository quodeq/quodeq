"""Dismissed snippet readers, the active-findings stream and the dismissed source stamp."""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.data.sqlite.state_store import SQLiteStateStore
from tests.data._findings_queries_helpers import _break_reopen_with_operational_error, _seed


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

    def test_read_dismissed_snippets_swallows_an_unreadable_db(self, tmp_path, monkeypatch):
        from quodeq.data.sqlite.findings_queries import read_dismissed_snippets

        _seed(tmp_path, req="X-1", file="src/a.py", line=10)
        _break_reopen_with_operational_error(monkeypatch)

        assert read_dismissed_snippets(tmp_path) == []

    def test_strict_variant_lets_an_unreadable_db_raise(self, tmp_path, monkeypatch):
        """The precedent memo needs to see the failure: the best-effort
        reader's [] would be remembered as "no dismissals" for this run."""
        from quodeq.data.sqlite.findings_queries import read_dismissed_snippets_strict

        _seed(tmp_path, req="X-1", file="src/a.py", line=10)
        _break_reopen_with_operational_error(monkeypatch)

        with pytest.raises(RuntimeError):
            read_dismissed_snippets_strict(tmp_path)

    def test_strict_variant_treats_a_missing_db_as_no_dismissals(self, tmp_path):
        from quodeq.data.sqlite.findings_queries import read_dismissed_snippets_strict

        assert read_dismissed_snippets_strict(tmp_path) == []

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

        rows = list(read_active_findings(tmp_path))

        assert [r["requirement"] for r in rows] == ["X-1", "X-2"]
        assert [r["verdict"] for r in rows] == ["violation", "compliance"]

    def test_limit_caps_rows_in_sql(self, tmp_path):
        from quodeq.data.sqlite.findings_queries import read_active_findings

        for i in (1, 2, 3):
            _seed(tmp_path, req=f"X-{i}", file=f"src/{i}.py", line=i)

        rows = list(read_active_findings(tmp_path, limit=2))

        assert [r["requirement"] for r in rows] == ["X-1", "X-2"]

    def test_streams_rows_instead_of_materializing_a_list(self, tmp_path):
        """The scores builder folds rows as they arrive; a big run must not
        be loaded into a second full copy before that fold starts."""
        import inspect

        from quodeq.data.sqlite.findings_queries import read_active_findings

        _seed(tmp_path)
        rows = read_active_findings(tmp_path)

        assert inspect.isgenerator(rows)
        assert [r["requirement"] for r in rows] == ["X-1"]

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

        assert list(read_active_findings(tmp_path)) == []


class TestDismissedSourceStamp:
    """Freshness key for the per-run precedent memo (context.precedent_fingerprint)."""

    def test_none_without_a_database(self, tmp_path):
        from quodeq.data.sqlite.findings_queries import dismissed_source_stamp

        assert dismissed_source_stamp(tmp_path) is None

    def test_changes_when_the_database_is_written(self, tmp_path):
        from quodeq.data.sqlite.findings_queries import dismissed_source_stamp

        _seed(tmp_path, req="X-1", file="src/a.py", line=10)
        before = dismissed_source_stamp(tmp_path)
        _seed(tmp_path, req="X-2", file="src/b.py", line=20, practice_id="P2")

        assert before is not None
        assert dismissed_source_stamp(tmp_path) != before

    def test_covers_the_wal_file(self, tmp_path):
        """Connections run in WAL mode: a write held in the WAL by another
        open connection leaves the main file's stat untouched."""
        from quodeq.data.sqlite.findings_queries import dismissed_source_stamp

        _seed(tmp_path, req="X-1", file="src/a.py", line=10)
        before = dismissed_source_stamp(tmp_path)
        (tmp_path / "evaluation.db-wal").write_bytes(b"pending frames")

        assert dismissed_source_stamp(tmp_path) != before

    def test_checkpoint_between_the_two_stats_still_changes_the_stamp(
        self, tmp_path, monkeypatch,
    ):
        """A checkpoint-on-close moves the pending frames into the main file
        and removes the WAL. Landing right after the first stat, it must not
        leave the stamp equal to the one taken before the dismissal: that
        is a stale memo hit. Reading the WAL first means the main-file stat
        that follows sees the checkpointed bytes."""
        from quodeq.data.sqlite.findings_queries import dismissed_source_stamp

        _seed(tmp_path, req="X-1", file="src/a.py", line=10)
        db, wal = tmp_path / "evaluation.db", tmp_path / "evaluation.db-wal"
        assert not wal.exists()
        settled = dismissed_source_stamp(tmp_path)
        wal.write_bytes(b"dismissal frames")  # committed, not yet checkpointed
        real_stat, stats = Path.stat, 0

        def stat_then_checkpoint(self, *args, **kwargs):
            nonlocal stats
            result = real_stat(self, *args, **kwargs)
            stats += 1
            if stats == 1:
                db.write_bytes(db.read_bytes() + b"frames")
                wal.unlink()
            return result

        monkeypatch.setattr(Path, "stat", stat_then_checkpoint)

        assert dismissed_source_stamp(tmp_path) != settled


def test_precedent_carries_no_database_dependency():
    """context/precedent.py must not import the sqlite connection helper."""
    import quodeq.context.precedent as precedent

    src = open(precedent.__file__).read()
    assert "open_evaluation_db" not in src
    assert "FROM findings" not in src
