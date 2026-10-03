"""Principle grades and files read persist next to the cached per-run scalars."""
from __future__ import annotations

from dataclasses import replace

import pytest

from quodeq.core.observability import NULL_LOG
from quodeq.core.types import DimensionResult
from quodeq.core.types.finding import Finding
from quodeq.core.types.report import PrincipleGrade
from quodeq.data.sqlite.score_cache_principles import principle_rows
from quodeq.data.sqlite.score_cache_rows import row_dimension, scalar_dimension
from quodeq.data.sqlite.score_cache_store import read_cached_rows, write_cached_rows
from quodeq.services.score_cache import make_cache_backed_fetcher, open_score_cache


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))


def _dims() -> list[DimensionResult]:
    return [
        DimensionResult(
            dimension="security", overall_score="7.0/10", overall_grade="Fair", files_read=42,
            source_file_count=120, quarantined_count=2, exit_reason="failure_streak",
            evidence_date="2026-01-01T00:00:00Z", discipline="python",
            principles=[PrincipleGrade("P1", "6.0/10", "Fair"), PrincipleGrade("P2", "8.0/10", "Good")],
        ),
        DimensionResult(
            dimension="reliability", overall_score="9.0/10", overall_grade="Good",
            principles=[PrincipleGrade("R1", None, None), PrincipleGrade(None, "1.0/10", "Poor")],
        ),
    ]


def _stored(conn, run_id: str, version: str) -> dict[str, list[tuple]]:
    rows = conn.execute(
        "SELECT dimension, principle, score, grade FROM run_principle_scalars"
        " WHERE project='proj' AND run_id=? AND version=? ORDER BY rowid", (run_id, version))
    out: dict[str, list[tuple]] = {}
    for dim, *grade in rows:
        out.setdefault(dim, []).append(tuple(grade))
    return out


_EXPECTED = {
    "security": [("P1", "6.0/10", "Fair"), ("P2", "8.0/10", "Good")],
    "reliability": [("R1", None, None)],
}


def test_principle_rows_skip_unnamed_principles():
    assert principle_rows(_dims()) == [
        ("security", "P1", "6.0/10", "Fair"), ("security", "P2", "8.0/10", "Good"),
        ("reliability", "R1", None, None),
    ]


class TestStore:
    def test_rows_persist_with_the_scalars(self):
        with open_score_cache() as conn:
            write_cached_rows(conn, "proj", "r1", "v1", _dims())
            stored = _stored(conn, "r1", "v1")
        assert stored == _EXPECTED

    def test_rows_are_keyed_by_run_and_version(self):
        with open_score_cache() as conn:
            write_cached_rows(conn, "proj", "r1", "v1", _dims())
            write_cached_rows(conn, "proj", "r2", "v2", _dims()[:1])
            first, second = _stored(conn, "r1", "v1"), _stored(conn, "r2", "v2")
        assert first == _EXPECTED
        assert second == {"security": _EXPECTED["security"]}

    def test_rewrite_replaces_the_runs_principle_rows(self):
        with open_score_cache() as conn:
            write_cached_rows(conn, "proj", "r1", "v1", _dims())
            write_cached_rows(conn, "proj", "r1", "v2", _dims()[1:])
            stale, fresh = _stored(conn, "r1", "v1"), _stored(conn, "r1", "v2")
        assert stale == {}
        assert fresh == {"reliability": _EXPECTED["reliability"]}

    def test_rows_read_back_with_their_principles(self):
        with open_score_cache() as conn:
            write_cached_rows(conn, "proj", "r1", "v1", _dims())
            back = read_cached_rows(conn, "proj", "r1", "v1")
        assert back is not None
        assert {d.dimension: d.principles for d in back} == {
            "security": _dims()[0].principles, "reliability": [PrincipleGrade("R1", None, None)],
        }

    def test_files_read_round_trips(self):
        with open_score_cache() as conn:
            write_cached_rows(conn, "proj", "r1", "v1", _dims())
            back = read_cached_rows(conn, "proj", "r1", "v1")
        assert {d.dimension: d.files_read for d in back} == {"security": 42, "reliability": None}

    def test_every_scalar_round_trips(self):
        with open_score_cache() as conn:
            write_cached_rows(conn, "proj", "r1", "v1", [row_dimension(d) for d in _dims()])
            back = {d.dimension: d for d in read_cached_rows(conn, "proj", "r1", "v1")}
        assert back["security"] == row_dimension(_dims()[0])
        bare = back["reliability"]
        assert (bare.source_file_count, bare.quarantined_count, bare.exit_reason, bare.evidence_date,
                bare.discipline) == (None, 0, None, None, None)

    def test_scalar_rows_still_read_back(self):
        with open_score_cache() as conn:
            write_cached_rows(conn, "proj", "r1", "v1", _dims())
            back = read_cached_rows(conn, "proj", "r1", "v1")
        assert [(d.dimension, d.overall_score) for d in back] == [("reliability", "9.0/10"), ("security", "7.0/10")]

    def test_schema_declares_the_table(self):
        with open_score_cache() as conn:
            cols = [row[1] for row in conn.execute("PRAGMA table_info(run_principle_scalars)")]
        assert cols == ["project", "run_id", "version", "dimension", "principle", "score", "grade"]


def test_scalar_dimension_drops_principles_and_files_read():
    served = scalar_dimension(_dims()[0])
    assert served.principles == [] and served.files_read is None


def test_row_dimension_is_the_dimension_without_its_findings():
    full = replace(_dims()[0], violations=[Finding(file="a.py", line=1, req="R1")],
                   compliance=[Finding(file="b.py", line=2, req="R2")])
    row = row_dimension(full)
    assert row.violations == [] and row.compliance == []
    assert replace(row, open_types=None) == replace(_dims()[0], open_types=None)
    assert row.open_types == 1


def test_cache_backed_fetcher_writes_principle_rows_on_a_miss():
    fetch = make_cache_backed_fetcher("proj", lambda _rid: "v1", lambda _rid: _dims(), log=NULL_LOG)
    served = fetch("r1")
    with open_score_cache() as conn:
        stored = _stored(conn, "r1", "v1")
    assert all(d.principles == [] for d in served)
    assert stored == _EXPECTED


def test_cache_backed_fetcher_serves_rows_and_the_trend_shape_from_one_read():
    calls: list[str] = []

    def base(rid: str) -> list[DimensionResult]:
        calls.append(rid)
        return _dims()

    fetch = make_cache_backed_fetcher("proj", lambda _rid: "v1", base, log=NULL_LOG)
    rows = fetch.rows("r1")
    served = fetch("r1")
    assert calls == ["r1"]
    assert [d.files_read for d in rows] == [42, None]
    assert [len(d.principles) for d in rows] == [2, 2]
    assert [d.files_read for d in served] == [None, None]
    assert all(d.principles == [] for d in served)
