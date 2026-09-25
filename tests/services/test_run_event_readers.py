"""Log-message parity tests for services/run_event_readers.py.

read_status is exercised end to end through api/_run_event_watcher.py's
compute_tick (tests/api/test_run_event_stream_ticks.py). read_dim_eval's
missing-file path only ever runs when the caller passes a dimension name
with no evaluation/<dim>.json (compute_tick never does -- it only reads
dimensions scan_completed_dimensions already found on disk), so it is
exercised directly here instead.
"""
from __future__ import annotations

import logging

from quodeq.services.run_event_readers import read_dim_eval
from quodeq.shared.log_sink import LoggerSink


def test_read_dim_eval_missing_file_logs_the_old_oserror_text(tmp_path, caplog):
    """Parity with the pre-move inline reader: a missing evaluation/<dim>.json
    logs the real OSError text ("[Errno 2] No such file or directory: ..."),
    not a made-up "file not found" string -- same logger, level and one
    record, since wiring.read_eval_report swallows that OSError into a plain
    None return rather than raising it."""
    logger = logging.getLogger("test.read_dim_eval")
    with caplog.at_level(logging.WARNING, logger="test.read_dim_eval"):
        result = read_dim_eval(tmp_path, "security", log=LoggerSink(logger))

    assert result is None
    assert len(caplog.records) == 1, [(r.name, r.message) for r in caplog.records]
    record = caplog.records[0]
    assert record.levelname == "WARNING"
    path = tmp_path / "evaluation" / "security.json"
    assert record.message == (
        f"dimension eval read failed at {path}: "
        f"[Errno 2] No such file or directory: '{path}'"
    )
