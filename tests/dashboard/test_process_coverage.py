"""Tests for quodeq.dashboard._process — process management."""
from __future__ import annotations

import json
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


class TestKillStaleActionApi:
    """The stale-kill must not execute a *live* API.

    Killing it unconditionally is what stranded the open window: its Flask
    server died under it, /api/projects never answered, and the app sat on the
    loading screen forever.
    """

    @staticmethod
    def _run(tmp_path, pid_file_body, *, healthy, request_port=7864):
        pid_file = tmp_path / "action_api.pid"
        pid_file.write_text(pid_file_body, encoding="utf-8")
        with patch("quodeq.dashboard._process._get_pid_file", return_value=pid_file), \
             patch("quodeq.dashboard._process.action_api_healthy", return_value=healthy) as health, \
             patch("quodeq.dashboard._process._is_port_open", return_value=False), \
             patch("quodeq.dashboard._process._terminate_pid") as kill:
            from quodeq.dashboard._process import _kill_stale_action_api
            _kill_stale_action_api("127.0.0.1", request_port)
        return kill, health, pid_file

    def test_healthy_api_is_left_alone(self, tmp_path):
        kill, _health, pid_file = self._run(
            tmp_path, json.dumps({"pid": 4242, "host": "127.0.0.1", "port": 7863}), healthy=True,
        )
        kill.assert_not_called()
        # The record must survive too, or the next launch loses track of it.
        assert json.loads(pid_file.read_text(encoding="utf-8"))["pid"] == 4242

    def test_health_is_checked_on_the_recorded_port_not_the_requested_one(self, tmp_path):
        """The two differ in exactly the case that matters.

        _choose_ui_port has already skipped the port the live API holds, so the
        launch asks for 7864 while the API to protect is on 7863.
        """
        _kill, health, _pid_file = self._run(
            tmp_path, json.dumps({"pid": 4242, "host": "127.0.0.1", "port": 7863}),
            healthy=True, request_port=7864,
        )
        health.assert_called_once_with("http://127.0.0.1:7863")

    def test_unhealthy_api_is_killed_and_record_removed(self, tmp_path):
        kill, _health, pid_file = self._run(
            tmp_path, json.dumps({"pid": 4242, "host": "127.0.0.1", "port": 7863}), healthy=False,
        )
        kill.assert_called_once_with(4242)
        assert not pid_file.exists()

    def test_legacy_bare_pid_file_falls_back_to_requested_endpoint(self, tmp_path):
        """Older versions wrote just the pid, with no endpoint to check."""
        kill, health, _pid_file = self._run(tmp_path, "4242", healthy=True)
        health.assert_called_once_with("http://127.0.0.1:7864")
        kill.assert_not_called()

    def test_legacy_bare_pid_file_unhealthy_is_killed(self, tmp_path):
        kill, _health, _pid_file = self._run(tmp_path, "4242", healthy=False)
        kill.assert_called_once_with(4242)

    @pytest.mark.parametrize("body", ["", "   ", "not-a-pid", '{"host": "127.0.0.1"}', "[1, 2]"])
    def test_unusable_record_kills_nothing(self, tmp_path, body):
        kill, _health, pid_file = self._run(tmp_path, body, healthy=False)
        kill.assert_not_called()
        assert not pid_file.exists()


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
