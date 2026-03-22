"""Tests for file priority scoring."""
from __future__ import annotations

from quodeq.analysis.subagents.priority import compute_base_score, compute_dimension_boost, compute_fan_in, load_priority_config


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


class TestComputeDimensionBoost:
    def test_security_keyword_match(self):
        assert compute_dimension_boost("src/auth_handler.py", "security") == 5

    def test_security_no_match(self):
        assert compute_dimension_boost("src/utils.py", "security") == 0

    def test_reliability_keyword_match(self):
        assert compute_dimension_boost("src/error_handler.py", "reliability") == 5

    def test_maintainability_uses_file_size(self):
        assert compute_dimension_boost("src/big.py", "maintainability", file_size=10000) == 5

    def test_maintainability_small_file(self):
        assert compute_dimension_boost("src/tiny.py", "maintainability", file_size=500) == 0

    def test_consolidated_max_across_dimensions(self):
        score = compute_dimension_boost("src/auth_handler.py", ["security", "maintainability"])
        assert score == 5

    def test_unknown_dimension(self):
        assert compute_dimension_boost("src/file.py", "unknown_dim") == 0


class TestComputeFanIn:
    def test_counts_python_imports(self, tmp_path):
        (tmp_path / "main.py").write_text("from auth import login\nimport utils\n")
        (tmp_path / "handler.py").write_text("from auth import verify\n")
        (tmp_path / "auth.py").write_text("# no imports\n")
        (tmp_path / "utils.py").write_text("# no imports\n")

        files = ["main.py", "handler.py", "auth.py", "utils.py"]
        fan_in = compute_fan_in(files, tmp_path, "python")
        assert fan_in.get("auth.py", 0) >= 2
        assert fan_in.get("utils.py", 0) >= 1

    def test_javascript_imports(self, tmp_path):
        (tmp_path / "app.js").write_text("import { foo } from './auth'\nconst bar = require('./utils')\n")
        (tmp_path / "auth.js").write_text("")
        (tmp_path / "utils.js").write_text("")

        files = ["app.js", "auth.js", "utils.js"]
        fan_in = compute_fan_in(files, tmp_path, "javascript")
        assert fan_in.get("auth.js", 0) >= 1
        assert fan_in.get("utils.js", 0) >= 1

    def test_no_imports_returns_empty(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1\n")
        fan_in = compute_fan_in(["a.py"], tmp_path, "python")
        assert fan_in == {} or all(v == 0 for v in fan_in.values())

    def test_unknown_language_returns_empty(self, tmp_path):
        fan_in = compute_fan_in(["a.xyz"], tmp_path, "cobol")
        assert fan_in == {}
