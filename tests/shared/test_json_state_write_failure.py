"""write_json_state: a write failure is fail-soft but must be visible.

The write is never worth crashing over (state files are advisory caches),
but a silent debug-level line means a real disk problem never surfaces
anywhere an operator would look. The failure is logged at WARNING.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from quodeq.shared.json_state import write_json_state


@dataclass
class _State:
    value: str = "default"


def test_write_failure_is_logged_at_warning_not_debug(tmp_path: Path, monkeypatch, caplog) -> None:
    import quodeq.shared.json_state as json_state_mod

    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(json_state_mod.tempfile, "mkstemp", boom)

    logger = logging.getLogger("quodeq.test.json_state_write_failure")
    path = tmp_path / "state.json"
    with caplog.at_level(logging.WARNING, logger=logger.name):
        write_json_state(_State(value="x"), path, "test", logger)  # must not raise

    assert not path.exists()
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("state write failed" in r.message for r in warnings)
