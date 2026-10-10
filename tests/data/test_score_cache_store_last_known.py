"""The project-card summary row is readable whatever version it was written under."""
from __future__ import annotations

from quodeq.data.sqlite.score_cache_db import open_score_cache
from quodeq.data.sqlite.score_cache_store import (
    read_last_project_summary,
    read_last_project_summary_cached,
    write_cached_project_summary,
)


def test_no_row_answers_none(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    with open_score_cache() as conn:
        assert read_last_project_summary(conn, "p") is None
    assert read_last_project_summary_cached("p") is None


def test_the_row_survives_a_version_change_until_rewritten(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    with open_score_cache() as conn:
        write_cached_project_summary(conn, "p", "v1", {"grade": "B", "score": 7.4, "files": 12})

    assert read_last_project_summary_cached("p") == {"grade": "B", "score": 7.4, "files": 12}

    with open_score_cache() as conn:
        write_cached_project_summary(conn, "p", "v2", {"grade": "C", "score": 6.1, "files": 12})
    assert read_last_project_summary_cached("p") == {"grade": "C", "score": 6.1, "files": 12}


def test_other_projects_rows_do_not_answer(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    with open_score_cache() as conn:
        write_cached_project_summary(conn, "other", "v1", {"grade": "A", "score": 9.0, "files": 3})
    assert read_last_project_summary_cached("p") is None
