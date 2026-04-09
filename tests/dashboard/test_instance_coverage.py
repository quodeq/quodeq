"""Extended tests for quodeq.dashboard._instance — edge cases and more coverage."""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.dashboard._instance import InstanceController


class TestInstanceControllerInit:
    def test_default_sock_path(self):
        with patch("quodeq.dashboard._instance._IS_WIN32", False):
            ctrl = InstanceController()
            assert ctrl._sock_path is not None
            ctrl.shutdown()

    def test_custom_sock_path(self, tmp_path):
        sock = tmp_path / "custom.sock"
        ctrl = InstanceController(sock_path=sock)
        assert ctrl._sock_path == sock


class TestTryAcquireUnix:
    def test_acquire_and_release(self, tmp_path):
        sock = tmp_path / "test.sock"
        ctrl = InstanceController(sock_path=sock)
        assert ctrl.try_acquire() is True
        assert sock.exists()
        ctrl.shutdown()
        assert not sock.exists()

    def test_second_instance_cannot_acquire(self, tmp_path):
        sock = tmp_path / "test.sock"
        ctrl1 = InstanceController(sock_path=sock)
        assert ctrl1.try_acquire() is True
        ctrl1.start_listening(on_reload=lambda url: None)

        ctrl2 = InstanceController(sock_path=sock)
        assert ctrl2.try_acquire() is False

        ctrl1.shutdown()

    def test_stale_socket_replaced(self, tmp_path):
        """A stale socket file (no listener) is cleaned up and replaced."""
        sock = tmp_path / "test.sock"
        sock.touch()
        ctrl = InstanceController(sock_path=sock)
        assert ctrl.try_acquire() is True
        ctrl.shutdown()


class TestSendReload:
    def test_send_and_receive(self, tmp_path):
        sock = tmp_path / "test.sock"
        received = []
        ctrl1 = InstanceController(sock_path=sock)
        ctrl1.try_acquire()
        ctrl1.start_listening(on_reload=lambda url: received.append(url))

        ctrl2 = InstanceController(sock_path=sock)
        ctrl2.try_acquire()  # returns False
        ctrl2.send_reload("http://localhost:9999")

        time.sleep(0.3)
        ctrl1.shutdown()
        assert received == ["http://localhost:9999"]

    def test_multiple_reloads(self, tmp_path):
        sock = tmp_path / "test.sock"
        received = []
        ctrl1 = InstanceController(sock_path=sock)
        ctrl1.try_acquire()
        ctrl1.start_listening(on_reload=lambda url: received.append(url))

        ctrl2 = InstanceController(sock_path=sock)
        ctrl2.try_acquire()
        ctrl2.send_reload("http://localhost:1111")
        # Wait long enough for the listener to accept and process the first connection
        time.sleep(1.5)
        ctrl2.send_reload("http://localhost:2222")
        time.sleep(0.5)

        ctrl1.shutdown()
        assert "http://localhost:1111" in received
        assert "http://localhost:2222" in received


class TestShutdown:
    def test_shutdown_idempotent(self, tmp_path):
        sock = tmp_path / "test.sock"
        ctrl = InstanceController(sock_path=sock)
        ctrl.try_acquire()
        ctrl.shutdown()
        ctrl.shutdown()  # should not raise

    def test_shutdown_without_acquire(self, tmp_path):
        sock = tmp_path / "test.sock"
        ctrl = InstanceController(sock_path=sock)
        ctrl.shutdown()  # should not raise

    def test_shutdown_cleans_socket(self, tmp_path):
        sock = tmp_path / "test.sock"
        ctrl = InstanceController(sock_path=sock)
        ctrl.try_acquire()
        assert sock.exists()
        ctrl.shutdown()
        assert not sock.exists()


class TestListenerThread:
    def test_listener_stops_on_shutdown(self, tmp_path):
        sock = tmp_path / "test.sock"
        ctrl = InstanceController(sock_path=sock)
        ctrl.try_acquire()
        ctrl.start_listening(on_reload=lambda url: None)
        assert ctrl._listen_thread is not None
        assert ctrl._listen_thread.is_alive()
        ctrl.shutdown()
        time.sleep(0.5)
        assert not ctrl._listen_thread.is_alive()

    def test_listener_handles_non_reload_data(self, tmp_path):
        """Listener should ignore data that doesn't start with 'reload:'."""
        sock = tmp_path / "test.sock"
        received = []
        ctrl = InstanceController(sock_path=sock)
        ctrl.try_acquire()
        ctrl.start_listening(on_reload=lambda url: received.append(url))

        # Send non-reload data using the controller's connect helper (handles long paths)
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        ctrl._connect_to_sock(client)
        client.sendall(b"not_a_reload_command")
        client.close()

        time.sleep(0.2)
        ctrl.shutdown()
        assert received == []


class TestConnectToSock:
    def test_connect_via_helper(self, tmp_path):
        """Connect using the controller's helper (handles long paths)."""
        sock_path = tmp_path / "s.sock"
        ctrl = InstanceController(sock_path=sock_path)
        ctrl.try_acquire()

        # Verify we can connect via the helper
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        ctrl._connect_to_sock(client)
        client.close()
        ctrl.shutdown()


class TestDefaultPaths:
    def test_default_sock_path(self):
        from quodeq.dashboard._instance import _default_sock_path
        path = _default_sock_path()
        assert path.name == "dashboard.sock"
        assert ".quodeq" in str(path)

    def test_default_sock_path_with_env(self, tmp_path):
        from quodeq.dashboard._instance import _default_sock_path
        with patch.dict("os.environ", {"QUODEQ_RUN_DIR": str(tmp_path / "custom_run")}):
            path = _default_sock_path()
            assert "custom_run" in str(path)

    def test_default_port_file(self):
        from quodeq.dashboard._instance import _default_port_file
        path = _default_port_file()
        assert path.name == "dashboard.port"
