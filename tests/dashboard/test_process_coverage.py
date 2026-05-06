"""Tests for quodeq.dashboard._process — process management."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestTerminatePid:
    # _terminate_pid reads quodeq.dashboard._process.IS_WIN32, which is
    # captured at import time from sys.platform — patching sys.platform
    # after import does not flip it. Patch the module attribute directly
    # so this test can run (and validate POSIX behaviour) on Windows CI too.
    @patch("quodeq.dashboard._process.IS_WIN32", False)
    @patch("os.kill")
    def test_unix(self, mock_kill):
        from quodeq.dashboard._process import _terminate_pid
        import signal
        _terminate_pid(1234)
        mock_kill.assert_called_once_with(1234, signal.SIGTERM)


class TestGetPidFile:
    def test_default(self):
        from quodeq.dashboard._process import _get_pid_file
        result = _get_pid_file(env={})
        assert result.name == "action_api.pid"

    def test_from_env(self, tmp_path):
        from quodeq.dashboard._process import _get_pid_file
        result = _get_pid_file(env={"QUODEQ_RUN_DIR": str(tmp_path)})
        assert result.parent == tmp_path

    def test_relative_path_raises(self):
        from quodeq.dashboard._process import _get_pid_file
        with pytest.raises(ValueError, match="absolute"):
            _get_pid_file(env={"QUODEQ_RUN_DIR": "relative/path"})


class TestWaitForProcess:
    def test_process_already_done(self):
        from quodeq.dashboard._process import _wait_for_process
        proc = MagicMock()
        proc.poll.return_value = 0
        _wait_for_process(proc)

    def test_process_waits(self):
        from quodeq.dashboard._process import _wait_for_process
        proc = MagicMock()
        proc.poll.side_effect = [None, 0]
        proc.wait.side_effect = [subprocess.TimeoutExpired("cmd", 5), 0]
        _wait_for_process(proc)
