"""Tests for API runner prompt assembly."""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.analysis.api_prompt_assembly import assemble_api_prompt


@pytest.fixture()
def src_dir(tmp_path):
    """Create a minimal source directory with two files."""
    (tmp_path / "main.py").write_text("def hello():\n    print('hi')\n")
    (tmp_path / "utils.py").write_text("def add(a, b):\n    return a + b\n")
    return tmp_path


@pytest.fixture()
def standards_text():
    return "M-MOD-1: Modules should have a single responsibility.\nS-CON-3: No hardcoded secrets."


class TestAssembleApiPrompt:
    """assemble_api_prompt bundles code + standards into a structured prompt."""

    def test_includes_source_files(self, src_dir, standards_text):
        prompt = assemble_api_prompt(
            source_files=[src_dir / "main.py", src_dir / "utils.py"],
            standards_text=standards_text,
            dimension="maintainability",
            repo_name="test-repo",
        )
        assert "main.py" in prompt
        assert "def hello():" in prompt
        assert "utils.py" in prompt
        assert "def add(a, b):" in prompt

    def test_includes_standards(self, src_dir, standards_text):
        prompt = assemble_api_prompt(
            source_files=[src_dir / "main.py"],
            standards_text=standards_text,
            dimension="security",
            repo_name="test-repo",
        )
        assert "M-MOD-1" in prompt
        assert "S-CON-3" in prompt

    def test_includes_dimension(self, src_dir, standards_text):
        prompt = assemble_api_prompt(
            source_files=[src_dir / "main.py"],
            standards_text=standards_text,
            dimension="security",
            repo_name="test-repo",
        )
        assert "security" in prompt.lower()

    def test_includes_json_schema(self, src_dir, standards_text):
        prompt = assemble_api_prompt(
            source_files=[src_dir / "main.py"],
            standards_text=standards_text,
            dimension="maintainability",
            repo_name="test-repo",
        )
        assert '"req"' in prompt
        assert '"severity"' in prompt
        assert '"violation"' in prompt

    def test_handles_unreadable_file_gracefully(self, src_dir, standards_text):
        missing = src_dir / "gone.py"
        prompt = assemble_api_prompt(
            source_files=[missing, src_dir / "main.py"],
            standards_text=standards_text,
            dimension="maintainability",
            repo_name="test-repo",
        )
        assert "def hello():" in prompt

    def test_returns_string(self, src_dir, standards_text):
        prompt = assemble_api_prompt(
            source_files=[src_dir / "main.py"],
            standards_text=standards_text,
            dimension="maintainability",
            repo_name="test-repo",
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_labels_test_file_with_role(self, tmp_path, standards_text):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_main.py").write_text("def test_x():\n    assert True\n")
        prompt = assemble_api_prompt(
            source_files=[tests_dir / "test_main.py"],
            standards_text=standards_text,
            dimension="maintainability",
            repo_name="test-repo",
            repo_root=tmp_path,
        )
        assert "tests/test_main.py (role: test)" in prompt

    def test_omits_role_label_for_prod_files(self, tmp_path, standards_text):
        src = tmp_path / "src"
        src.mkdir()
        (src / "server.py").write_text("def hello():\n    pass\n")
        prompt = assemble_api_prompt(
            source_files=[src / "server.py"],
            standards_text=standards_text,
            dimension="maintainability",
            repo_name="test-repo",
            repo_root=tmp_path,
        )
        assert "(role:" not in prompt
