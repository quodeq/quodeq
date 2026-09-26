import logging
import socket
import time
from pathlib import Path
from unittest.mock import patch

from quodeq.dashboard._instance import InstanceController


def _send_reload(sock_path: Path, url: str) -> None:
    """Send a reload as a second instance does: learn the owner's address
    first (on Windows try_acquire reads the TCP port file), then send."""
    sender = InstanceController(sock_path)
    assert sender.try_acquire() is False
    sender.send_reload(url)


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


def test_listener_survives_an_on_reload_failure_and_keeps_serving(tmp_path: Path):
    """R-FT-7 -- an exception from on_reload (anything past the socket errors
    _serve_one already handles) must not kill the listener thread; the next
    reload must still reach it."""
    sock_path = tmp_path / "test.sock"
    received: list[str] = []

    def _on_reload(url: str) -> None:
        received.append(url)
        if len(received) == 1:
            raise RuntimeError("boom")

    ctrl1 = InstanceController(sock_path)
    assert ctrl1.try_acquire() is True
    ctrl1.start_listening(on_reload=_on_reload)

    _send_reload(sock_path, "http://localhost:7863/first")
    time.sleep(0.2)
    _send_reload(sock_path, "http://localhost:7863/second")
    time.sleep(0.2)

    ctrl1.shutdown()

    assert received == [
        "http://localhost:7863/first",
        "http://localhost:7863/second",
    ]


def test_listener_logs_a_warning_on_an_on_reload_failure(tmp_path: Path, caplog):
    sock_path = tmp_path / "test.sock"

    def _on_reload(_url: str) -> None:
        raise RuntimeError("boom")

    ctrl1 = InstanceController(sock_path)
    assert ctrl1.try_acquire() is True
    with caplog.at_level(logging.WARNING, logger="quodeq.dashboard._instance"):
        ctrl1.start_listening(on_reload=_on_reload)
        _send_reload(sock_path, "http://localhost:7863")
        time.sleep(0.2)
    ctrl1.shutdown()

    matching = [r for r in caplog.records if "reload listener failed" in r.getMessage()]
    assert matching, [r.getMessage() for r in caplog.records]
    assert any(r.exc_info for r in matching)


def test_listener_survives_a_connection_reset_and_closes_the_connection(tmp_path: Path):
    """Review fix -- an OSError from conn.recv (e.g. a peer reset) is a
    per-connection failure, not the listening socket dying: it must not stop
    the loop, and the connection must still be closed."""
    sock_path = tmp_path / "test.sock"
    received: list[str] = []

    ctrl1 = InstanceController(sock_path)
    assert ctrl1.try_acquire() is True
    ctrl1.start_listening(on_reload=received.append)

    real_recv = socket.socket.recv
    calls = {"n": 0}
    raised_on: dict[str, socket.socket] = {}

    def _flaky_recv(self, *args, **kwargs):
        # Drain the client's payload first so its sendall() completes cleanly
        # (closing conn unread would race the client with a spurious
        # BrokenPipeError), then fail the first read that carried a reload.
        # A liveness probe sends nothing, so it is never the one reset,
        # whenever the listener thread gets to it.
        data = real_recv(self, *args, **kwargs)
        if data and calls["n"] == 0:
            calls["n"] += 1
            raised_on["conn"] = self
            raise ConnectionResetError("peer reset")
        return data

    sender = InstanceController(sock_path)
    assert sender.try_acquire() is False
    with patch.object(socket.socket, "recv", _flaky_recv):
        sender.send_reload("http://localhost:7863/first")
        time.sleep(0.2)
        sender.send_reload("http://localhost:7863/second")
        time.sleep(0.2)

    ctrl1.shutdown()

    # The reset connection never reached on_reload, but the listener kept
    # going and served the next one.
    assert received == ["http://localhost:7863/second"]
    # Closed despite the recv failure: fileno() is -1 once a socket is closed.
    assert raised_on["conn"].fileno() == -1
