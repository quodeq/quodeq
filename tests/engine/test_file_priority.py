"""Tests for file priority scoring."""
from __future__ import annotations

from quodeq.analysis.subagents.priority import load_priority_config


class TestLoadPriorityConfig:
    def test_loads_default_config(self):
        config = load_priority_config()
        assert "path_boost" in config
        assert "dimension_keywords" in config
        assert "import_patterns" in config
        assert config["default_path_score"] == 2

    def test_cached_on_second_call(self):
        c1 = load_priority_config()
        c2 = load_priority_config()
        assert c1 is c2  # same object, cached
