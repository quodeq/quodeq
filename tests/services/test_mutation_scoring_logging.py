"""resolve_default_run_id / rescore_run must not swallow failures silently."""
from __future__ import annotations

import logging

import pytest
from unittest.mock import patch

from quodeq.services.mutation_rescore import rescore_run, resolve_default_run_id


def test_resolve_default_run_id_logs_list_runs_failure(caplog, tmp_path):
    with patch(
        "quodeq.services._mutation_scoring.list_runs",
        side_effect=OSError("disk unavailable"),
    ), caplog.at_level(logging.WARNING):
        result = resolve_default_run_id(str(tmp_path), "proj-1")
    assert result is None
    assert any("proj-1" in r.message for r in caplog.records)


def test_resolve_default_run_id_lets_an_out_of_scope_error_propagate():
    """list_runs' real surface is (OSError, ValueError) -- validate_path_segment
    plus the filesystem reads it wraps. Anything else is a genuine bug in
    list_runs itself and must surface, not be silently remapped to None."""
    with patch(
        "quodeq.services._mutation_scoring.list_runs",
        side_effect=RuntimeError("unexpected bug"),
    ), pytest.raises(RuntimeError, match="unexpected bug"):
        resolve_default_run_id("/tmp", "proj-1")


def test_rescore_run_logs_and_falls_back_to_none_on_a_locked_evaluation_db(
    tmp_path, recording_log,
):
    """get_scores_raw's SQL grade-tables path opens evaluation.db through
    open_evaluation_db, which wraps a locked/IO-erroring connect as
    RuntimeError -- a real failure mode, not a hypothetical one (mirrors the
    "database is locked" scenario grade_formula's apply already covers)."""
    (tmp_path / "proj" / "run-1").mkdir(parents=True)
    with patch(
        "quodeq.services.scoring.get_scores_raw",
        side_effect=RuntimeError("Could not open evaluation database at ...: locked"),
    ):
        result = rescore_run(str(tmp_path), "proj", "run-1", log=recording_log)
    assert result is None
    assert any("proj/run-1" in msg for msg in recording_log.warning_messages)


def test_rescore_run_lets_an_out_of_scope_error_propagate(tmp_path, recording_log):
    """A bug in get_scores_raw outside the traced (sqlite3.Error, OSError,
    json.JSONDecodeError, ValueError, KeyError, RuntimeError) surface must
    surface to the caller instead of silently turning into a dropped rescore."""
    (tmp_path / "proj" / "run-1").mkdir(parents=True)
    with patch(
        "quodeq.services.scoring.get_scores_raw",
        side_effect=AttributeError("unexpected bug"),
    ), pytest.raises(AttributeError, match="unexpected bug"):
        rescore_run(str(tmp_path), "proj", "run-1", log=recording_log)
