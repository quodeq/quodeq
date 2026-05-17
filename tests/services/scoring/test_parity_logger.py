from __future__ import annotations

import logging
import os
from unittest.mock import patch

import pytest

from quodeq.services.scoring._parity_logger import is_enabled, log_divergence_if_any


def test_is_enabled_false_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("QUODEQ_GRADE_PARITY_LOG", raising=False)
    assert is_enabled() is False


def test_is_enabled_true_when_set_to_1(monkeypatch) -> None:
    monkeypatch.setenv("QUODEQ_GRADE_PARITY_LOG", "1")
    assert is_enabled() is True


def test_is_enabled_false_when_set_to_other(monkeypatch) -> None:
    monkeypatch.setenv("QUODEQ_GRADE_PARITY_LOG", "true")
    assert is_enabled() is False


def test_no_log_when_payloads_match(caplog) -> None:
    payload_a = {"dimensions": [{"dimension": "Security", "overallScore": "7.0/10"}], "summary": {}}
    payload_b = {"dimensions": [{"dimension": "Security", "overallScore": "7.0/10"}], "summary": {}}
    with caplog.at_level(logging.WARNING):
        log_divergence_if_any(legacy=payload_a, sql=payload_b, run_id="r1")
    assert not any("parity" in r.message.lower() for r in caplog.records)


def test_logs_when_dimension_score_diverges(caplog) -> None:
    payload_a = {"dimensions": [{"dimension": "Security", "overallScore": "7.0/10"}], "summary": {}}
    payload_b = {"dimensions": [{"dimension": "Security", "overallScore": "8.0/10"}], "summary": {}}
    with caplog.at_level(logging.WARNING):
        log_divergence_if_any(legacy=payload_a, sql=payload_b, run_id="r1")
    matching = [r for r in caplog.records if "parity" in r.message.lower()]
    assert len(matching) == 1
    # The log should include the run_id, both values, and the dimension name.
    assert "r1" in matching[0].getMessage()
    assert "Security" in matching[0].getMessage()


def test_logs_when_dimension_only_in_legacy(caplog) -> None:
    """Dimension present in legacy but missing in SQL -> log it."""
    payload_a = {"dimensions": [{"dimension": "Security", "overallScore": "7.0/10"}], "summary": {}}
    payload_b = {"dimensions": [], "summary": {}}
    with caplog.at_level(logging.WARNING):
        log_divergence_if_any(legacy=payload_a, sql=payload_b, run_id="r1")
    assert any("parity" in r.message.lower() for r in caplog.records)


def test_logs_when_dimension_only_in_sql(caplog) -> None:
    """Dimension present in SQL but missing in legacy -> log it."""
    payload_a = {"dimensions": [], "summary": {}}
    payload_b = {"dimensions": [{"dimension": "Security", "overallScore": "7.0/10"}], "summary": {}}
    with caplog.at_level(logging.WARNING):
        log_divergence_if_any(legacy=payload_a, sql=payload_b, run_id="r1")
    assert any("parity" in r.message.lower() for r in caplog.records)


def test_no_log_when_payloads_empty(caplog) -> None:
    """Both empty payloads -> no divergence, no log."""
    payload_a = {"dimensions": [], "summary": {}}
    payload_b = {"dimensions": [], "summary": {}}
    with caplog.at_level(logging.WARNING):
        log_divergence_if_any(legacy=payload_a, sql=payload_b, run_id="r1")
    assert not any("parity" in r.message.lower() for r in caplog.records)


def test_get_scores_raw_runs_parity_check_when_flag_set(tmp_path, caplog, monkeypatch) -> None:
    """When QUODEQ_GRADE_PARITY_LOG=1, get_scores_raw runs the legacy path and logs divergences."""
    monkeypatch.setenv("QUODEQ_GRADE_PARITY_LOG", "1")

    # Seed + project a run.
    from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
    from quodeq.core.events.writer import EventLogWriter
    from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository
    project_dir = tmp_path / "myproject"
    run_dir = project_dir / "runs" / "r1"
    run_dir.mkdir(parents=True)
    EventLogWriter(run_dir / "events.jsonl").emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Security",
        file="a.py", line=10, reason="r", req="R1", severity="high",
    )))
    SqliteFindingsRepository(run_dir).list_by_dimension("Security")  # project

    import logging
    from quodeq.services.scoring import get_scores_raw
    with caplog.at_level(logging.WARNING):
        result = get_scores_raw(tmp_path, "myproject", "r1")

    # We expect a parity warning because:
    #   - SQL returns a populated Security dimension
    #   - Legacy reads from FS grade files (which don't exist in this test) -> empty
    # That mismatch is exactly what the parity logger flags.
    parity_logs = [r for r in caplog.records if "parity" in r.message.lower()]
    assert len(parity_logs) >= 1
    assert "Security" in parity_logs[0].getMessage()


def test_get_scores_raw_skips_parity_check_when_flag_unset(tmp_path, caplog, monkeypatch) -> None:
    monkeypatch.delenv("QUODEQ_GRADE_PARITY_LOG", raising=False)

    from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
    from quodeq.core.events.writer import EventLogWriter
    from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository
    project_dir = tmp_path / "myproject"
    run_dir = project_dir / "runs" / "r1"
    run_dir.mkdir(parents=True)
    EventLogWriter(run_dir / "events.jsonl").emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Security",
        file="a.py", line=10, reason="r", req="R1", severity="high",
    )))
    SqliteFindingsRepository(run_dir).list_by_dimension("Security")

    import logging
    from quodeq.services.scoring import get_scores_raw
    with caplog.at_level(logging.WARNING):
        get_scores_raw(tmp_path, "myproject", "r1")

    parity_logs = [r for r in caplog.records if "parity" in r.message.lower()]
    assert parity_logs == []  # nothing logged when flag is unset
