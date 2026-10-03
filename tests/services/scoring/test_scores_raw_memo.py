"""The SQL grade-tables read behind ``get_scores_raw`` is memoized per run.

The run page, the detail refill and the dimension eval read the same run,
often within one screen. The first read pays the database; the rest copy.
The memo holds while the run's ``evaluation.db`` and ``events.jsonl`` are
unchanged, and hands out copies so a caller's edits never reach the memo.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.data.events.writer import EventLogWriter
from quodeq.services.scoring import get_scores_raw
from tests.perf._budget_fixture import PROJECT, count_io, seed_project

_RUN = "20260101T000000"


@pytest.fixture()
def reports(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "evaluations"))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "index.db"))
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "score_cache.db"))
    root = tmp_path / "evaluations"
    seed_project(root)
    return root


def _security(response: dict) -> dict:
    return next(d for d in response["dimensions"] if d["dimension"] == "security")


def test_second_read_of_an_unchanged_run_opens_nothing(reports, monkeypatch) -> None:
    first = get_scores_raw(reports, PROJECT, _RUN)
    with count_io(monkeypatch) as counts:
        second = get_scores_raw(reports, PROJECT, _RUN)
    assert second == first
    assert counts["evaluation_db_opens"] == 0
    assert counts["eval_report_reads"] == 0


def test_callers_get_their_own_copy(reports) -> None:
    first = get_scores_raw(reports, PROJECT, _RUN)
    _security(first)["violations"].clear()
    first["summary"]["mutated"] = True
    second = get_scores_raw(reports, PROJECT, _RUN)
    assert _security(second)["violations"]
    assert "mutated" not in second["summary"]


def test_new_events_miss_the_memo_and_are_projected(reports) -> None:
    before = len(_security(get_scores_raw(reports, PROJECT, _RUN))["violations"])
    run_dir = reports / PROJECT / _RUN
    log = run_dir / "events.jsonl"
    EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="Confidentiality", verdict="violation", dimension="security",
        file="new.py", line=1, reason="r", req="S-NEW-1", severity="major", snippet="new()",
    )))
    # The log's stamp is mtime and size; a same-tick append still grows the size.
    os.utime(log, ns=(time.time_ns(), time.time_ns()))
    after = _security(get_scores_raw(reports, PROJECT, _RUN))["violations"]
    assert len(after) == before + 1
    assert any(v["file"] == "new.py" for v in after)
