"""load_priority_config must not swallow a missing/malformed config silently."""
from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import patch

from quodeq.analysis.subagents.priority_config import (
    load_priority_config,
    reset_priority_config_cache,
)


def test_load_priority_config_logs_missing_file(caplog, tmp_path):
    fake_paths = SimpleNamespace(root=tmp_path)  # no config/file_priority.json here
    reset_priority_config_cache()
    try:
        with patch(
            "quodeq.analysis.subagents.priority_config.default_paths",
            return_value=fake_paths,
        ), caplog.at_level(logging.WARNING):
            result = load_priority_config()
        assert result == {}
        assert any("file_priority" in r.message.lower() for r in caplog.records)
    finally:
        reset_priority_config_cache()
