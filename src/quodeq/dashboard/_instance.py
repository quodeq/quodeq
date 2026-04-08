"""Single-instance controller using unix domain sockets."""
from __future__ import annotations

import logging
import os
import socket
import threading
from pathlib import Path
from typing import Callable

_logger = logging.getLogger(__name__)
_SOCK_TIMEOUT = 1.0
_RELOAD_PREFIX = "reload:"


def _default_sock_path() -> Path:
    run_dir = Path(os.environ.get("QUODEQ_RUN_DIR", Path.home() / ".quodeq" / "run"))
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / "dashboard.sock"


class InstanceController:
    """Manage single-instance lifecycle via a unix domain socket.

    First instance: ``try_acquire()`` returns True, call ``start_listening()``.
    Second instance: ``try_acquire()`` returns False, call ``send_reload(url)``.
    """

    def __init__(self, sock_path: Path | None = None) -> None:
        self._sock_path = sock_path or _default_sock_path()
        self._server_sock: socket.socket | None = None
        self._listen_thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()

    def _connect_to_sock(self, sock: socket.socket) -> None:
        """Connect *sock* to self._sock_path, handling long-path macOS limit."""
        path_str = str(self._sock_path)
        if len(path_str) <= 100:
            sock.connect(path_str)
            return
        orig_cwd = os.getcwd()
        try:
            os.chdir(str(self._sock_path.parent))
            sock.connect(self._sock_path.name)
        finally:
            os.chdir(orig_cwd)

    def try_acquire(self) -> bool:
        """Try to become the primary instance. Return True if acquired."""
        if self._sock_path.exists():
            try:
                probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                probe.settimeout(_SOCK_TIMEOUT)
                self._connect_to_sock(probe)
                probe.close()
                return False
            except (ConnectionRefusedError, OSError):
                _logger.debug("Removing stale socket %s", self._sock_path)
                self._sock_path.unlink(missing_ok=True)

        self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._bind_server_sock()
        self._server_sock.listen(1)
        self._server_sock.settimeout(_SOCK_TIMEOUT)
        return True

    def _bind_server_sock(self) -> None:
        """Bind the server socket, working around macOS's 104-char AF_UNIX limit."""
        path_str = str(self._sock_path)
        if len(path_str) <= 100:
            self._server_sock.bind(path_str)
            return
        # Path too long for AF_UNIX on macOS — bind using a relative name by
        # temporarily switching to the socket's parent directory.
        orig_cwd = os.getcwd()
        try:
            os.chdir(str(self._sock_path.parent))
            self._server_sock.bind(self._sock_path.name)
        finally:
            os.chdir(orig_cwd)

    def start_listening(self, on_reload: Callable[[str], None]) -> None:
        """Start a background thread that listens for reload commands."""
        def _listen() -> None:
            while not self._shutdown_event.is_set():
                try:
                    conn, _ = self._server_sock.accept()
                    data = conn.recv(4096).decode("utf-8", errors="replace")
                    conn.close()
                    if data.startswith(_RELOAD_PREFIX):
                        url = data[len(_RELOAD_PREFIX):]
                        _logger.info("Received reload request: %s", url)
                        on_reload(url)
                except socket.timeout:
                    continue
                except OSError:
                    if not self._shutdown_event.is_set():
                        _logger.debug("Listener socket error", exc_info=True)
                    break

        self._listen_thread = threading.Thread(target=_listen, daemon=True)
        self._listen_thread.start()

    def send_reload(self, url: str) -> None:
        """Send a reload command to the running instance."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(_SOCK_TIMEOUT)
        self._connect_to_sock(sock)
        sock.sendall(f"{_RELOAD_PREFIX}{url}".encode("utf-8"))
        sock.close()

    def shutdown(self) -> None:
        """Stop listening and clean up the socket file."""
        self._shutdown_event.set()
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
        if self._listen_thread:
            self._listen_thread.join(timeout=2.0)
        self._sock_path.unlink(missing_ok=True)
