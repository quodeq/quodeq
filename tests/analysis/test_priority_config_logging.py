"""load_priority_config must not swallow a missing/malformed config silently."""
from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import patch

from quodeq.analysis.subagents.priority_config import (
    load_priority_config,
    reset_priority_config_cache,
)
from quodeq.analysis.subagents.priority_scoring import compute_base_score
from quodeq.config.paths import default_paths

# src/ path boost (5) plus the entry-point boost (3), from the shipped values.
_SRC_ENTRY_POINT_SCORE = 8


def test_load_priority_config_logs_missing_file(caplog, tmp_path):
    fake_paths = SimpleNamespace(root=tmp_path)  # no config/file_priority.json here
    reset_priority_config_cache()
    try:
        with patch(
            "quodeq.analysis.subagents.priority_config.default_paths",
            return_value=fake_paths,
        ), caplog.at_level(logging.WARNING):
            result = load_priority_config()
        assert "default_path_score" in result
        assert any("file_priority" in r.message.lower() for r in caplog.records)
    finally:
        reset_priority_config_cache()


def test_a_missing_config_file_still_scores_files(tmp_path):
    fake_paths = SimpleNamespace(root=tmp_path)  # no config/file_priority.json here
    reset_priority_config_cache()
    try:
        with patch(
            "quodeq.analysis.subagents.priority_config.default_paths",
            return_value=fake_paths,
        ):
            assert compute_base_score("src/quodeq/api/app.py") == _SRC_ENTRY_POINT_SCORE
    finally:
        reset_priority_config_cache()


def test_a_config_file_that_is_not_an_object_falls_back_to_defaults(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "file_priority.json").write_text("[]", encoding="utf-8")
    reset_priority_config_cache()
    try:
        with patch(
            "quodeq.analysis.subagents.priority_config.default_paths",
            return_value=SimpleNamespace(root=tmp_path),
        ):
            assert compute_base_score("src/main.py") == _SRC_ENTRY_POINT_SCORE
    finally:
        reset_priority_config_cache()


def test_the_fallback_defaults_match_the_shipped_config(tmp_path):
    shipped = json.loads(
        (default_paths().root / "config" / "file_priority.json").read_text(encoding="utf-8"))
    reset_priority_config_cache()
    try:
        with patch(
            "quodeq.analysis.subagents.priority_config.default_paths",
            return_value=SimpleNamespace(root=tmp_path),
        ):
            assert load_priority_config() == shipped
    finally:
        reset_priority_config_cache()
