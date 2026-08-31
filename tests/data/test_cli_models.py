"""The CLI ``/models`` discovery adapter is the single place that shells
out to an AI CLI client to list its models. Policy (allowlist, isalnum
guard, output parsing) stays in ``services/tooling_mixin.py``.
"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch


class TestRunCliModelsCommand:
    def test_not_installed_returns_empty(self):
        from quodeq.data.cli_models import run_cli_models_command

        with patch("shutil.which", return_value=None):
            assert run_cli_models_command("claude", timeout_s=8) == ""

    def test_returns_stdout_on_success(self):
        from quodeq.data.cli_models import run_cli_models_command

        with patch("shutil.which", return_value="/usr/bin/claude"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="model-a\nmodel-b\n")
            assert run_cli_models_command("claude", timeout_s=8) == "model-a\nmodel-b\n"

    def test_nonzero_returncode_returns_empty(self):
        from quodeq.data.cli_models import run_cli_models_command

        with patch("shutil.which", return_value="/usr/bin/claude"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="error")
            assert run_cli_models_command("claude", timeout_s=8) == ""

    def test_timeout_returns_empty(self):
        from quodeq.data.cli_models import run_cli_models_command

        with patch("shutil.which", return_value="/usr/bin/claude"), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=8)):
            assert run_cli_models_command("claude", timeout_s=8) == ""

    def test_oserror_returns_empty(self):
        from quodeq.data.cli_models import run_cli_models_command

        with patch("shutil.which", return_value="/usr/bin/claude"), \
             patch("subprocess.run", side_effect=OSError("boom")):
            assert run_cli_models_command("claude", timeout_s=8) == ""
