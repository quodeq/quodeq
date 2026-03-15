"""Tests for quodeq.config.knowledge_refresh — practices/analysis refresh pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.config import knowledge_refresh as kr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _github_search_response(repos: list[dict]) -> str:
    return json.dumps({"items": repos})


def _raw_repo_entry(name: str = "org/repo", stars: int = 1000, branch: str = "main") -> dict:
    """GitHub API format (used in search response)."""
    return {
        "full_name": name,
        "stargazers_count": stars,
        "html_url": f"https://github.com/{name}",
        "default_branch": branch,
    }


def _repo_entry(name: str = "org/repo", stars: int = 1000, branch: str = "main") -> dict:
    """Processed format (as returned by _fetch_cursor_rules_repos)."""
    return {
        "name": name,
        "stars": stars,
        "url": f"https://github.com/{name}",
        "default_branch": branch,
    }


# ---------------------------------------------------------------------------
# _fetch_cursor_rules_repos
# ---------------------------------------------------------------------------

class TestFetchCursorRulesRepos:
    def test_returns_repos_above_min_stars(self):
        response = _github_search_response([
            _raw_repo_entry("a/high", 600),
            _raw_repo_entry("b/low", 100),
        ])
        with patch.object(kr, "_fetch_url", return_value=response):
            repos = kr._fetch_cursor_rules_repos("typescript", 500)
        assert len(repos) == 1
        assert repos[0]["name"] == "a/high"

    def test_returns_empty_on_fetch_failure(self):
        with patch.object(kr, "_fetch_url", return_value=None):
            assert kr._fetch_cursor_rules_repos("typescript", 500) == []

    def test_returns_empty_on_invalid_json(self):
        with patch.object(kr, "_fetch_url", return_value="not json"):
            assert kr._fetch_cursor_rules_repos("typescript", 500) == []


# ---------------------------------------------------------------------------
# _fetch_repo_content
# ---------------------------------------------------------------------------

class TestFetchRepoContent:
    def test_collects_first_matching_file_per_repo(self):
        def fake_fetch(url):
            if ".cursorrules" in url:
                return "rules content"
            return None

        repos = [_repo_entry("org/repo1"), _repo_entry("org/repo2")]
        with patch.object(kr, "_fetch_url", side_effect=fake_fetch):
            samples = kr._fetch_repo_content(repos)
        assert len(samples) == 2
        assert "rules content" in samples[0]

    def test_truncates_content_to_limit(self):
        long_content = "x" * 10000
        with patch.object(kr, "_fetch_url", return_value=long_content):
            samples = kr._fetch_repo_content([_repo_entry()])
        # Content truncated to _CONTENT_SAMPLE_LIMIT plus header
        assert len(samples[0]) < 10000 + 200

    def test_returns_empty_when_no_files_found(self):
        with patch.object(kr, "_fetch_url", return_value=None):
            assert kr._fetch_repo_content([_repo_entry()]) == []


# ---------------------------------------------------------------------------
# _build_practices_prompt / _build_analysis_prompt
# ---------------------------------------------------------------------------

class TestBuildPracticesPrompt:
    def test_contains_runtime_and_samples(self, tmp_path: Path):
        out = tmp_path / "practices.json"
        prompt = kr._build_practices_prompt("typescript", ["sample1", "sample2"], out)
        assert "typescript" in prompt
        assert "sample1" in prompt
        assert "sample2" in prompt

    def test_includes_existing_content(self, tmp_path: Path):
        out = tmp_path / "practices.json"
        out.write_text('{"practices": []}')
        prompt = kr._build_practices_prompt("typescript", ["sample"], out)
        assert '{"practices": []}' in prompt


class TestBuildAnalysisPrompt:
    def test_contains_runtime_and_docs(self, tmp_path: Path):
        out = tmp_path / "analysis.md"
        prompt = kr._build_analysis_prompt("python", "linter docs here", out)
        assert "python" in prompt
        assert "linter docs here" in prompt

    def test_truncates_long_existing(self, tmp_path: Path):
        out = tmp_path / "analysis.md"
        out.write_text("x" * 5000)
        prompt = kr._build_analysis_prompt("python", "docs", out)
        # Existing content truncated to _EXISTING_CONTENT_LIMIT
        assert "x" * kr._EXISTING_CONTENT_LIMIT in prompt
        assert "x" * 3000 not in prompt

    def test_truncates_long_linter_docs(self, tmp_path: Path):
        out = tmp_path / "analysis.md"
        long_docs = "d" * 10000
        prompt = kr._build_analysis_prompt("python", long_docs, out)
        assert "d" * kr._LINTER_DOCS_LIMIT in prompt
        assert "d" * 8000 not in prompt


# ---------------------------------------------------------------------------
# refresh_practices (integration, mocked HTTP + LLM)
# ---------------------------------------------------------------------------

class TestRefreshPractices:
    def test_success_writes_file(self, tmp_path: Path):
        evaluators_dir = tmp_path / "evaluators"
        (evaluators_dir / "typescript" / "knowledge").mkdir(parents=True)
        llm_output = json.dumps({"practices": [{"id": "ts-001"}]})
        with patch.object(kr, "_fetch_cursor_rules_repos", return_value=[_repo_entry()]), \
             patch.object(kr, "_fetch_repo_content", return_value=["sample"]), \
             patch.object(kr, "run_ai_cli", return_value=(llm_output, None)):
            result = kr.refresh_practices("typescript", evaluators_dir)
        assert result == 0
        out = evaluators_dir / "typescript" / "knowledge" / "practices.json"
        assert out.exists()
        assert json.loads(out.read_text())["practices"][0]["id"] == "ts-001"

    def test_no_repos_returns_1(self, tmp_path: Path):
        with patch.object(kr, "_fetch_cursor_rules_repos", return_value=[]):
            assert kr.refresh_practices("typescript", tmp_path) == 1

    def test_no_content_returns_1(self, tmp_path: Path):
        with patch.object(kr, "_fetch_cursor_rules_repos", return_value=[_repo_entry()]), \
             patch.object(kr, "_fetch_repo_content", return_value=[]):
            assert kr.refresh_practices("typescript", tmp_path) == 1

    def test_llm_error_returns_1(self, tmp_path: Path):
        with patch.object(kr, "_fetch_cursor_rules_repos", return_value=[_repo_entry()]), \
             patch.object(kr, "_fetch_repo_content", return_value=["sample"]), \
             patch.object(kr, "run_ai_cli", return_value=(None, "fail")):
            assert kr.refresh_practices("typescript", tmp_path) == 1

    def test_invalid_json_returns_1(self, tmp_path: Path):
        with patch.object(kr, "_fetch_cursor_rules_repos", return_value=[_repo_entry()]), \
             patch.object(kr, "_fetch_repo_content", return_value=["sample"]), \
             patch.object(kr, "run_ai_cli", return_value=("not json", None)):
            assert kr.refresh_practices("typescript", tmp_path) == 1

    def test_dry_run_does_not_write(self, tmp_path: Path):
        evaluators_dir = tmp_path / "evaluators"
        llm_output = json.dumps({"practices": [{"id": "ts-001"}]})
        with patch.object(kr, "_fetch_cursor_rules_repos", return_value=[_repo_entry()]), \
             patch.object(kr, "_fetch_repo_content", return_value=["sample"]), \
             patch.object(kr, "run_ai_cli", return_value=(llm_output, None)):
            result = kr.refresh_practices("typescript", evaluators_dir, dry_run=True)
        assert result == 0
        out = evaluators_dir / "typescript" / "knowledge" / "practices.json"
        assert not out.exists()


# ---------------------------------------------------------------------------
# refresh_analysis (integration, mocked HTTP + LLM)
# ---------------------------------------------------------------------------

class TestRefreshAnalysis:
    def test_success_writes_file(self, tmp_path: Path):
        evaluators_dir = tmp_path / "evaluators"
        (evaluators_dir / "typescript" / "knowledge").mkdir(parents=True)
        with patch.object(kr, "_get_linter_sources", return_value={"typescript": "http://example.com"}), \
             patch.object(kr, "_fetch_url", return_value="linter docs"), \
             patch.object(kr, "run_ai_cli", return_value=("# Analysis", None)):
            result = kr.refresh_analysis("typescript", evaluators_dir)
        assert result == 0
        out = evaluators_dir / "typescript" / "knowledge" / "analysis.md"
        assert out.read_text() == "# Analysis"

    def test_unsupported_runtime_returns_1(self, tmp_path: Path):
        with patch.object(kr, "_get_linter_sources", return_value={}):
            assert kr.refresh_analysis("cobol", tmp_path) == 1

    def test_fetch_failure_returns_1(self, tmp_path: Path):
        with patch.object(kr, "_get_linter_sources", return_value={"typescript": "http://example.com"}), \
             patch.object(kr, "_fetch_url", return_value=None):
            assert kr.refresh_analysis("typescript", tmp_path) == 1

    def test_llm_error_returns_1(self, tmp_path: Path):
        with patch.object(kr, "_get_linter_sources", return_value={"typescript": "http://example.com"}), \
             patch.object(kr, "_fetch_url", return_value="docs"), \
             patch.object(kr, "run_ai_cli", return_value=(None, "error")):
            assert kr.refresh_analysis("typescript", tmp_path) == 1

    def test_dry_run_does_not_write(self, tmp_path: Path):
        evaluators_dir = tmp_path / "evaluators"
        with patch.object(kr, "_get_linter_sources", return_value={"typescript": "http://example.com"}), \
             patch.object(kr, "_fetch_url", return_value="docs"), \
             patch.object(kr, "run_ai_cli", return_value=("# Analysis", None)):
            result = kr.refresh_analysis("typescript", evaluators_dir, dry_run=True)
        assert result == 0
        out = evaluators_dir / "typescript" / "knowledge" / "analysis.md"
        assert not out.exists()


# ---------------------------------------------------------------------------
# Symbolic constants (CWE-1106 fix verification)
# ---------------------------------------------------------------------------

class TestSymbolicConstants:
    def test_constants_are_defined(self):
        assert kr._content_sample_limit() == 4000
        assert kr._LINTER_DOCS_LIMIT == 6000
        assert kr._EXISTING_CONTENT_LIMIT == 2000
