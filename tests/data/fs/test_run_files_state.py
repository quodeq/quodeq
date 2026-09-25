"""``read_run_state``: status.json's ``state`` field as a ``RunState``.

Sits on top of ``read_run_status_json`` (parse-error/non-dict -> ``{}``); an
unrecognized ``state`` string (corrupt file, or a schema this code predates)
also degrades to None rather than raising, matching this module's
never-raise contract.
"""
from __future__ import annotations

from quodeq.core.run.state import RunState
from quodeq.data.fs.run_files import read_run_state


def test_reads_state(tmp_path):
    (tmp_path / "status.json").write_text('{"schema_version": 2, "state": "done"}')
    assert read_run_state(tmp_path) is RunState.DONE


def test_missing_or_bad_is_none(tmp_path):
    assert read_run_state(tmp_path) is None
    (tmp_path / "status.json").write_text("[1]")
    assert read_run_state(tmp_path) is None
    (tmp_path / "status.json").write_text('{"state": "bogus"}')
    assert read_run_state(tmp_path) is None


def test_legacy_spelling_still_parses(tmp_path):
    """Older status.json files spelled DONE as "complete"/"completed"/"finished"."""
    (tmp_path / "status.json").write_text('{"state": "complete"}')
    assert read_run_state(tmp_path) is RunState.DONE
