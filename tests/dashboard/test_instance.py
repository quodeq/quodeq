import threading
import time
from pathlib import Path

from quodeq.dashboard._instance import InstanceController


def test_first_instance_acquires_lock(tmp_path: Path):
    sock_path = tmp_path / "test.sock"
    ctrl = InstanceController(sock_path)
    assert ctrl.try_acquire() is True
    ctrl.shutdown()


def test_second_instance_sends_reload(tmp_path: Path):
    sock_path = tmp_path / "test.sock"
    received = []

    ctrl1 = InstanceController(sock_path)
    assert ctrl1.try_acquire() is True
    ctrl1.start_listening(on_reload=lambda url: received.append(url))

    ctrl2 = InstanceController(sock_path)
    assert ctrl2.try_acquire() is False
    ctrl2.send_reload("http://localhost:7863")

    # Give the listener thread time to process
    time.sleep(0.2)
    ctrl1.shutdown()

    assert received == ["http://localhost:7863"]


def test_stale_socket_is_cleaned_up(tmp_path: Path):
    sock_path = tmp_path / "test.sock"
    # Create a stale socket file (not a real socket)
    sock_path.touch()

    ctrl = InstanceController(sock_path)
    assert ctrl.try_acquire() is True
    ctrl.shutdown()


def test_shutdown_removes_socket(tmp_path: Path):
    sock_path = tmp_path / "test.sock"
    ctrl = InstanceController(sock_path)
    ctrl.try_acquire()
    ctrl.shutdown()
    assert not sock_path.exists()
