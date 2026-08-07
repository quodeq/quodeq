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


def test_probe_does_not_bind_so_a_child_can_own_the_socket(tmp_path: Path):
    """The launcher probes; the window process it spawns is what binds.

    When the launcher bound instead, the child could never acquire, its
    listener died on an unbound socket, and reloads went nowhere.
    """
    sock_path = tmp_path / "test.sock"
    launcher = InstanceController(sock_path)

    assert launcher.probe_existing() is False
    assert not sock_path.exists()

    window = InstanceController(sock_path)
    assert window.try_acquire() is True
    window.shutdown()


def test_probe_detects_a_live_instance(tmp_path: Path):
    sock_path = tmp_path / "test.sock"
    owner = InstanceController(sock_path)
    assert owner.try_acquire() is True
    owner.start_listening(on_reload=lambda _url: None)

    assert InstanceController(sock_path).probe_existing() is True
    owner.shutdown()


def test_probe_clears_a_stale_socket(tmp_path: Path):
    sock_path = tmp_path / "test.sock"
    sock_path.touch()  # left behind by a crashed instance

    assert InstanceController(sock_path).probe_existing() is False
    assert not sock_path.exists()


def test_non_owner_shutdown_keeps_the_live_socket(tmp_path: Path):
    """A controller that only probed must not delete the winner's socket."""
    sock_path = tmp_path / "test.sock"
    owner = InstanceController(sock_path)
    owner.try_acquire()
    owner.start_listening(on_reload=lambda _url: None)

    loser = InstanceController(sock_path)
    assert loser.try_acquire() is False
    loser.shutdown()

    assert sock_path.exists()
    assert InstanceController(sock_path).probe_existing() is True
    owner.shutdown()


def test_start_listening_refuses_an_unacquired_socket(tmp_path: Path):
    """Reported, not silently swallowed by a thread that dies on accept().

    This is the failure that filled webview.log with AttributeError while the
    reload channel looked installed.
    """
    ctrl = InstanceController(tmp_path / "test.sock")
    assert ctrl.start_listening(on_reload=lambda _url: None) is False
    assert ctrl._listen_thread is None


def test_start_listening_reports_success_when_acquired(tmp_path: Path):
    ctrl = InstanceController(tmp_path / "test.sock")
    ctrl.try_acquire()
    assert ctrl.start_listening(on_reload=lambda _url: None) is True
    ctrl.shutdown()
