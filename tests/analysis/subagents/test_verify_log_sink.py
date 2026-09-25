"""``load_previous_findings_for_dimension`` logs through an injected sink.

The reader used to log via ``quodeq.shared.logging.log_info`` -- a
module-global helper, not the ``log: LogSink`` inner layers accept
(``core/observability.py``). These tests pin the conversion: the default
sink is silent, and an injected sink captures the "no previous evaluation"
line.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from quodeq.analysis.subagents.verify import load_previous_findings_for_dimension
from tests.conftest import RecordingLog


def _config(tmp_path: Path) -> MagicMock:
    config = MagicMock()
    config.options.verify_findings = True
    config.src = tmp_path
    return config


def test_default_log_sink_is_silent(tmp_path, capsys):
    result = load_previous_findings_for_dimension(
        _config(tmp_path), "security", tmp_path / "evidence",
    )
    assert result == []
    assert capsys.readouterr().out == ""


def test_injected_sink_records_no_previous_evaluation_line(tmp_path):
    log = RecordingLog()
    result = load_previous_findings_for_dimension(
        _config(tmp_path), "security", tmp_path / "evidence", log=log,
    )
    assert result == []
    assert any("No previous evaluation" in m for m in log.info_messages)


def test_quiet_suppresses_the_injected_sink_too(tmp_path):
    log = RecordingLog()
    load_previous_findings_for_dimension(
        _config(tmp_path), "security", tmp_path / "evidence", quiet=True, log=log,
    )
    assert log.info_messages == []
