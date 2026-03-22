import subprocess
from unittest.mock import patch

import pytest

from quodeq.shared.prereqs import check_node, check_npm, check_claude_code, check_dashboard_prereqs, check_evaluate_prereqs


class TestCheckNode:
    def test_missing_node_raises(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="Node.js"):
                check_node()

    def test_old_node_raises(self):
        result = subprocess.CompletedProcess([], 0, stdout="16.20.0\n")
        with patch("subprocess.run", return_value=result):
            with pytest.raises(RuntimeError, match="18"):
                check_node()

    def test_valid_node_passes(self):
        result = subprocess.CompletedProcess([], 0, stdout="v20.11.0\n")
        with patch("subprocess.run", return_value=result):
            check_node()


class TestCheckNpm:
    def test_missing_npm_raises(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="npm"):
                check_npm()

    def test_old_npm_raises(self):
        result = subprocess.CompletedProcess([], 0, stdout="8.19.0\n")
        with patch("subprocess.run", return_value=result):
            with pytest.raises(RuntimeError, match="9"):
                check_npm()

    def test_valid_npm_passes(self):
        result = subprocess.CompletedProcess([], 0, stdout="10.2.0\n")
        with patch("subprocess.run", return_value=result):
            check_npm()


class TestCheckClaudeCode:
    def test_missing_claude_raises(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="Claude Code"):
                check_claude_code()

    def test_valid_claude_passes(self):
        result = subprocess.CompletedProcess([], 0, stdout="1.0.0\n")
        with patch("subprocess.run", return_value=result):
            check_claude_code()


class TestCompositeChecks:
    def test_dashboard_prereqs_checks_node_and_npm(self):
        node_result = subprocess.CompletedProcess([], 0, stdout="v20.11.0\n")
        npm_result = subprocess.CompletedProcess([], 0, stdout="10.2.0\n")
        with patch("subprocess.run", side_effect=[node_result, npm_result]):
            check_dashboard_prereqs()

    def test_evaluate_prereqs_checks_claude(self):
        result = subprocess.CompletedProcess([], 0, stdout="1.0.0\n")
        with patch("subprocess.run", return_value=result):
            check_evaluate_prereqs()
