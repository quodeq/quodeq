"""Tests for file priority scoring."""
from __future__ import annotations

from unittest.mock import patch

from quodeq.analysis.subagents.priority import (
    compute_base_score,
    compute_dimension_boost,
    compute_fan_in,
    compute_git_scores,
    compute_previous_violations,
    load_priority_config,
    prioritize_files,
)


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


class TestComputeGitScores:
    def test_parses_git_log(self, tmp_path):
        mock_output = "abc123abc123abc123abc123abc123abc123abcd\n2026-03-20 10:00:00 +0000\nfile1.py\nfile2.py\n\ndef456def456def456def456def456def456defg\n2026-03-10 10:00:00 +0000\nfile1.py\n\n"
        with patch("quodeq.analysis.subagents.priority._run_git_log", return_value=mock_output):
            scores = compute_git_scores(["file1.py", "file2.py"], tmp_path)
        # file1.py has 2 commits, file2.py has 1
        assert scores.get("file1.py", 0) > scores.get("file2.py", 0)

    def test_git_not_available(self, tmp_path):
        with patch("quodeq.analysis.subagents.priority._run_git_log", return_value=None):
            scores = compute_git_scores(["file1.py"], tmp_path)
        assert scores == {}

    def test_recent_file_gets_recency_boost(self, tmp_path):
        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        old = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        mock_output = f"a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1\n{today} 10:00:00 +0000\nrecent.py\n\nb2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2\n{old} 10:00:00 +0000\nold.py\n\n"
        with patch("quodeq.analysis.subagents.priority._run_git_log", return_value=mock_output):
            scores = compute_git_scores(["recent.py", "old.py"], tmp_path)
        assert scores.get("recent.py", 0) >= scores.get("old.py", 0)


class TestComputePreviousViolations:
    def test_counts_violations_per_file(self, tmp_path):
        findings = [
            {"p": "Confidentiality", "d": "security", "t": "violation", "file": "auth.py", "line": 1},
            {"p": "Confidentiality", "d": "security", "t": "violation", "file": "auth.py", "line": 5},
            {"p": "Integrity", "d": "security", "t": "violation", "file": "routes.py", "line": 10},
            {"p": "Integrity", "d": "security", "t": "compliance", "file": "utils.py", "line": 1},
        ]
        with patch("quodeq.analysis.subagents.priority.load_previous_findings_for_dimension", return_value=findings):
            counts = compute_previous_violations(None, tmp_path, "security")
        assert counts.get("auth.py", 0) == 2
        assert counts.get("routes.py", 0) == 1
        assert counts.get("utils.py", 0) == 0

    def test_no_previous_run(self, tmp_path):
        with patch("quodeq.analysis.subagents.priority.load_previous_findings_for_dimension", return_value=[]):
            counts = compute_previous_violations(None, tmp_path, "security")
        assert counts == {}

    def test_consolidated_merges_dimensions(self, tmp_path):
        def mock_load(config, dim, evidence_dir, **kwargs):
            if dim == "security":
                return [{"t": "violation", "file": "auth.py", "line": 1}]
            elif dim == "maintainability":
                return [{"t": "violation", "file": "big.py", "line": 1}]
            return []
        with patch("quodeq.analysis.subagents.priority.load_previous_findings_for_dimension", side_effect=mock_load):
            counts = compute_previous_violations(None, tmp_path, ["security", "maintainability"])
        assert counts.get("auth.py", 0) >= 1
        assert counts.get("big.py", 0) >= 1


class TestPrioritizeFiles:
    def test_returns_sorted_by_score_descending(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "src" / "important.py").write_text("x" * 100)
        (tmp_path / "tests" / "boring.py").write_text("x" * 10)

        files = ["tests/boring.py", "src/important.py"]
        result = prioritize_files(files, tmp_path, "security")
        assert result[0] == "src/important.py"

    def test_all_files_preserved(self, tmp_path):
        files = [f"file{i}.py" for i in range(20)]
        for f in files:
            (tmp_path / f).write_text("")
        result = prioritize_files(files, tmp_path, "security")
        assert set(result) == set(files)
        assert len(result) == 20

    def test_dimension_affects_order(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "auth.py").write_text("x" * 100)
        (tmp_path / "src" / "utils.py").write_text("x" * 100)

        files = ["src/utils.py", "src/auth.py"]
        result = prioritize_files(files, tmp_path, "security")
        assert result[0] == "src/auth.py"

    def test_consolidated_uses_max_dimension_boost(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "auth.py").write_text("x")
        (tmp_path / "src" / "error_handler.py").write_text("x")

        files = ["src/auth.py", "src/error_handler.py"]
        result = prioritize_files(files, tmp_path, ["security", "reliability"])
        assert len(result) == 2


class TestPrioritizationIntegration:
    def test_list_source_files_returns_prioritized(self, tmp_path):
        from quodeq.analysis.subagents.runner import _list_source_files
        from quodeq.analysis.runner import RunConfig, AnalysisOptions
        from quodeq.analysis.manifest import AnalysisTarget, SourceManifest

        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "src" / "auth.py").write_text("x" * 100)
        (tmp_path / "tests" / "test_stuff.py").write_text("x" * 100)

        target = AnalysisTarget(
            name="python", language="python", category="backend",
            source_files=["tests/test_stuff.py", "src/auth.py"],
            total_files=2,
        )
        config = RunConfig(
            src=tmp_path, language="python",
            options=AnalysisOptions(),
            target=target,
            manifest=SourceManifest(targets=[target], total_files=2),
        )
        files, _ = _list_source_files(config, "security")
        # src/auth.py should come before tests/test_stuff.py
        assert files.index("src/auth.py") < files.index("tests/test_stuff.py")
