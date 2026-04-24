"""Tests for quodeq.analysis._process — subprocess management and heartbeat."""
from __future__ import annotations

import signal
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


class TestKillTree:
    @patch("sys.platform", "darwin")
    @patch("os.killpg")
    @patch("os.getpgid", return_value=1234)
    def test_unix_kills_process_group(self, mock_getpgid, mock_killpg):
        from quodeq.analysis._process import _kill_tree
        _kill_tree(1234)
        mock_killpg.assert_called_once_with(1234, signal.SIGTERM)

    @patch("sys.platform", "darwin")
    @patch("os.killpg", side_effect=ProcessLookupError)
    @patch("os.getpgid", return_value=1234)
    @patch("os.kill")
    def test_unix_fallback_to_kill(self, mock_kill, mock_getpgid, mock_killpg):
        from quodeq.analysis._process import _kill_tree
        _kill_tree(1234)
        mock_kill.assert_called_once_with(1234, signal.SIGTERM)

    @patch("sys.platform", "darwin")
    @patch("os.killpg", side_effect=ProcessLookupError)
    @patch("os.getpgid", return_value=1234)
    @patch("os.kill", side_effect=ProcessLookupError)
    def test_unix_both_fail(self, mock_kill, mock_getpgid, mock_killpg):
        from quodeq.analysis._process import _kill_tree
        _kill_tree(1234)  # should not raise

    @patch("sys.platform", "win32")
    @patch("subprocess.run")
    def test_windows_taskkill(self, mock_run):
        from quodeq.analysis._process import _kill_tree
        _kill_tree(5678)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "taskkill" in args
        assert "5678" in args


class TestTerminateProcess:
    def test_clean_termination(self):
        from quodeq.analysis._process import _terminate_process
        proc = MagicMock()
        proc.pid = 123
        proc.wait.return_value = 0
        with patch("quodeq.analysis._process._kill_tree"):
            _terminate_process(proc)
            proc.wait.assert_called_once()

    def test_timeout_kills(self):
        from quodeq.analysis._process import _terminate_process
        proc = MagicMock()
        proc.pid = 123
        proc.wait.side_effect = [subprocess.TimeoutExpired("cmd", 10), None]
        with patch("quodeq.analysis._process._kill_tree") as mock_kill:
            _terminate_process(proc)
            assert mock_kill.call_count == 2  # SIGTERM + SIGKILL

    def test_double_timeout_force_kill(self):
        from quodeq.analysis._process import _terminate_process
        proc = MagicMock()
        proc.pid = 123
        proc.wait.side_effect = subprocess.TimeoutExpired("cmd", 10)
        with patch("quodeq.analysis._process._kill_tree"):
            _terminate_process(proc)
            proc.kill.assert_called_once()


class TestRunWithHeartbeat:
    def test_process_exits_immediately(self, tmp_path):
        from quodeq.analysis._process import _run_with_heartbeat
        from quodeq.analysis._config import AnalysisConfig
        proc = MagicMock()
        proc.poll.return_value = 0
        cfg = AnalysisConfig(heartbeat_interval=1, heartbeat_callback=None, max_duration=None, jsonl_file=None)
        stream = tmp_path / "stream.jsonl"
        stream.write_text("")
        result = _run_with_heartbeat(proc, cfg, stream)
        assert result is False

    def test_heartbeat_callback(self, tmp_path):
        from quodeq.analysis._process import _run_with_heartbeat
        from quodeq.analysis._config import AnalysisConfig
        proc = MagicMock()
        proc.poll.side_effect = [None, 0]
        proc.wait.side_effect = subprocess.TimeoutExpired("cmd", 1)
        callback = MagicMock()
        cfg = AnalysisConfig(heartbeat_interval=1, heartbeat_callback=callback, max_duration=None, jsonl_file=None)
        stream = tmp_path / "stream.jsonl"
        stream.write_text("")
        _run_with_heartbeat(proc, cfg, stream)
        callback.assert_called_once()

    def test_timeout_terminates(self, tmp_path):
        from quodeq.analysis._process import _run_with_heartbeat
        from quodeq.analysis._config import AnalysisConfig
        proc = MagicMock()
        proc.poll.side_effect = [None, None, 0]
        proc.wait.side_effect = [subprocess.TimeoutExpired("cmd", 1), subprocess.TimeoutExpired("cmd", 1), 0]
        cfg = AnalysisConfig(heartbeat_interval=1, heartbeat_callback=None, max_duration=1, jsonl_file=None)
        stream = tmp_path / "stream.jsonl"
        stream.write_text("")
        with patch("quodeq.analysis._process._terminate_process"):
            result = _run_with_heartbeat(proc, cfg, stream)
            assert result is True

    def test_cancellation_terminates_mid_wait(self, tmp_path):
        """When cancellation is requested mid-inference, the subprocess is terminated
        and the loop exits after that tick — without waiting for max_duration."""
        from quodeq.analysis._process import _run_with_heartbeat
        from quodeq.analysis._config import AnalysisConfig
        from quodeq.shared import cancellation

        cancellation.reset()
        proc = MagicMock()
        # Subprocess never exits on its own — without cancel support, the loop hangs.
        proc.poll.return_value = None

        wait_calls = [0]

        def fake_wait(*args, **kwargs):
            wait_calls[0] += 1
            if wait_calls[0] == 1:
                cancellation.request_cancel()
                raise subprocess.TimeoutExpired("cmd", 1)
            # If the loop misbehaves and keeps waiting after cancel, fail fast
            # instead of hanging the test run.
            raise AssertionError("heartbeat loop did not exit after cancel")

        proc.wait = fake_wait
        cfg = AnalysisConfig(
            heartbeat_interval=1, heartbeat_callback=None,
            max_duration=None, jsonl_file=None,
        )
        stream = tmp_path / "stream.jsonl"
        stream.write_text("")
        try:
            with patch("quodeq.analysis._process._terminate_process") as mock_term:
                _run_with_heartbeat(proc, cfg, stream)
                mock_term.assert_called_once_with(proc)
                assert wait_calls[0] == 1
        finally:
            cancellation.reset()


class TestCheckProcessResult:
    def test_zero_exit_ok(self, tmp_path):
        from quodeq.analysis._process import _check_process_result
        proc = MagicMock()
        proc.returncode = 0
        _check_process_result(proc, tmp_path / "err.log")  # should not raise

    def test_nonzero_exit_raises(self, tmp_path):
        from quodeq.analysis._process import _check_process_result, AnalysisError
        proc = MagicMock()
        proc.returncode = 1
        err_file = tmp_path / "err.log"
        err_file.write_text("something went wrong")
        with pytest.raises(AnalysisError, match="code 1"):
            _check_process_result(proc, err_file)

    def test_nonzero_no_stderr(self, tmp_path):
        from quodeq.analysis._process import _check_process_result, AnalysisError
        proc = MagicMock()
        proc.returncode = 2
        with pytest.raises(AnalysisError, match="code 2"):
            _check_process_result(proc, tmp_path / "missing.log")
