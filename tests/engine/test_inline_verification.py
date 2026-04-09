"""Tests for inline verification flow."""
from quodeq.analysis.subagents._finding_classifier import classify_findings
from quodeq.analysis.subagents._verification import _load_and_filter_previous
from unittest.mock import patch, MagicMock


def test_classify_splits_by_queue_membership():
    needs_verify = [
        {"file": "a.py", "p": "S", "t": "violation", "line": 1, "reason": "r1"},
        {"file": "b.py", "p": "S", "t": "violation", "line": 2, "reason": "r2"},
        {"file": "c.py", "p": "S", "t": "violation", "line": 3, "reason": "r3"},
    ]
    queue_files = {"a.py", "c.py"}
    inline, mini = classify_findings(needs_verify, queue_files)
    assert {f["file"] for f in inline} == {"a.py", "c.py"}
    assert {f["file"] for f in mini} == {"b.py"}


@patch("quodeq.analysis.subagents.verify.load_previous_findings_for_dimension")
def test_load_and_filter_returns_empty_when_no_previous(mock_load, tmp_path):
    mock_load.return_value = []
    config = MagicMock()
    config.src = tmp_path
    config.options.incremental_file_filter = None
    result = _load_and_filter_previous(config, "security", tmp_path)
    assert result == []
