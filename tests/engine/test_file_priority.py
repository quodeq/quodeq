"""Tests for file priority scoring."""
from __future__ import annotations

from quodeq.analysis.subagents.priority import compute_base_score, load_priority_config


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


class TestComputeBaseScore:
    def test_src_directory_high_score(self):
        score = compute_base_score("src/quodeq/runner.py")
        assert score >= 5

    def test_test_directory_low_score(self):
        score = compute_base_score("tests/test_runner.py")
        assert score <= 2

    def test_unknown_path_gets_default(self):
        score = compute_base_score("random/file.py")
        assert score == 2

    def test_entry_point_boost(self):
        score_entry = compute_base_score("src/main.py")
        score_normal = compute_base_score("src/utils.py")
        assert score_entry > score_normal

    def test_category_boost_backend(self):
        score = compute_base_score("src/controller.py", category="backend")
        score_plain = compute_base_score("src/utils.py", category="backend")
        assert score > score_plain

    def test_category_boost_mobile(self):
        score = compute_base_score("src/LoginActivity.java", category="mobile")
        score_plain = compute_base_score("src/Utils.java", category="mobile")
        assert score > score_plain

    def test_no_category(self):
        score = compute_base_score("src/file.py", category=None)
        assert score >= 0
