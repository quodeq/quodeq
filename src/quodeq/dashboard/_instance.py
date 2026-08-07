"""Single-instance controller — unix socket on macOS/Linux, TCP localhost on Windows."""
from __future__ import annotations

import logging
import os
import socket
import sys
import threading
from pathlib import Path
from typing import Callable

_logger = logging.getLogger(__name__)
_SOCK_TIMEOUT = 0.5
_RELOAD_PREFIX = "reload:"
_MAX_UNIX_SOCK_PATH_LEN = 100
_TCP_LOCALHOST = "127.0.0.1"
_RECV_BUFFER_SIZE = 4096
# listen(1) is too tight on macOS: the probe inside try_acquire() and a
# follow-up send_reload() on the same path can fill the 1-slot backlog
# before the listener thread drains it, returning ECONNREFUSED. Linux
# silently rounds up so this only surfaces on Darwin. A small backlog is
# plenty — we only ever expect a handful of pending reloads.
_LISTEN_BACKLOG = 8
_IS_WIN32 = sys.platform == "win32"
_WIN_PORT_FILE = "dashboard.port"


def _default_sock_path() -> Path:
    run_dir = Path(os.environ.get("QUODEQ_RUN_DIR", Path.home() / ".quodeq" / "run"))
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / "dashboard.sock"


def _default_port_file() -> Path:
    run_dir = Path(os.environ.get("QUODEQ_RUN_DIR", Path.home() / ".quodeq" / "run"))
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / _WIN_PORT_FILE


class InstanceController:
    """Manage single-instance lifecycle.

    Uses unix domain sockets on macOS/Linux, TCP localhost on Windows.

    First instance: ``try_acquire()`` returns True, call ``start_listening()``.
    Second instance: ``try_acquire()`` returns False, call ``send_reload(url)``.
    """

    def __init__(self, sock_path: Path | None = None) -> None:
        if _IS_WIN32:
            self._port_file = sock_path or _default_port_file()
            self._sock_path = self._port_file  # for compatibility with _server.py
            self._tcp_port: int | None = None
        else:
            self._sock_path = sock_path or _default_sock_path()
        self._server_sock: socket.socket | None = None
        self._listen_thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()

    @property
    def sock_path(self) -> Path:
        """Public accessor for the socket/port-file path."""
        return self._sock_path

    # ── Unix socket helpers (macOS/Linux) ──

    def _sock_op(self, sock: socket.socket, op_name: str) -> None:
        """Connect or bind a unix socket, using chdir for long paths."""
        op = getattr(sock, op_name)
        path_str = str(self._sock_path)
        if len(path_str) <= _MAX_UNIX_SOCK_PATH_LEN:
            op(path_str)
            return
        orig_cwd = os.getcwd()
        try:
            os.chdir(str(self._sock_path.parent))
            op(self._sock_path.name)
        finally:
            os.chdir(orig_cwd)

    def _connect_to_sock(self, sock: socket.socket) -> None:
        self._sock_op(sock, "connect")

    def _bind_server_sock(self) -> None:
        self._sock_op(self._server_sock, "bind")

    # ── Public API ──

    def probe_existing(self) -> bool:
        """Return True if a live primary instance is already listening.

        Unlike ``try_acquire`` this never binds, so the caller can leave the
        socket free for a *child* process to own — which is what the native
        path does: the webview window process is the one that must react to a
        reload, so it owns the listener (see ``_server._serve_native``). A
        socket/port file left behind by a crashed instance is removed here, so
        the follow-up bind by that child still succeeds.
        """
        if _IS_WIN32:
            return self._probe_tcp()
        return self._probe_unix()

    def _probe_unix(self) -> bool:
        if not self._sock_path.exists():
            return False
        try:
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            probe.settimeout(_SOCK_TIMEOUT)
            self._connect_to_sock(probe)
            probe.close()
            return True
        except (ConnectionRefusedError, OSError):
            _logger.debug("Removing stale socket %s", self._sock_path)
            self._sock_path.unlink(missing_ok=True)
            return False

    def _probe_tcp(self) -> bool:
        if not self._port_file.exists():
            return False
        try:
            port = int(self._port_file.read_text(encoding="utf-8").strip())
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.settimeout(_SOCK_TIMEOUT)
                probe.connect((_TCP_LOCALHOST, port))
            self._tcp_port = port
            return True
        except (ConnectionRefusedError, OSError, ValueError):
            _logger.debug("Removing stale port file %s", self._port_file)
            self._port_file.unlink(missing_ok=True)
            return False

    def try_acquire(self) -> bool:
        """Try to become the primary instance. Return True if acquired."""
        if _IS_WIN32:
            return self._try_acquire_tcp()
        return self._try_acquire_unix()

    def _try_acquire_unix(self) -> bool:
        if self._probe_unix():
            return False

        self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._bind_server_sock()
        self._server_sock.listen(_LISTEN_BACKLOG)
        self._server_sock.settimeout(_SOCK_TIMEOUT)
        return True

    def _try_acquire_tcp(self) -> bool:
        """Windows: use TCP localhost with port stored in a file."""
        if self._probe_tcp():
            return False

        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.bind((_TCP_LOCALHOST, 0))
        self._tcp_port = self._server_sock.getsockname()[1]
        self._server_sock.listen(_LISTEN_BACKLOG)
        self._server_sock.settimeout(_SOCK_TIMEOUT)
        self._port_file.write_text(str(self._tcp_port), encoding="utf-8")
        return True

    def start_listening(self, on_reload: Callable[[str], None]) -> bool:
        """Start a background thread that listens for reload commands.

        Returns False (and starts nothing) when this controller never acquired
        the socket. Without that guard every ``accept()`` raises
        ``AttributeError`` on the ``None`` socket, the thread dies on the first
        iteration, and the traceback is the only trace — which is exactly how
        the reload channel stayed silently dead: the caller had no way to tell
        listening from not-listening.
        """
        if self._server_sock is None:
            _logger.warning(
                "Not listening for reloads: socket was never acquired "
                "(call try_acquire first)",
            )
            return False

        def _listen() -> None:
            while not self._shutdown_event.is_set():
                try:
                    conn, _ = self._server_sock.accept()
                    data = conn.recv(_RECV_BUFFER_SIZE).decode("utf-8", errors="replace")
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
        return True

    def send_reload(self, url: str) -> None:
        """Send a reload command to the running instance."""
        self._send(f"{_RELOAD_PREFIX}{url}")

    def send_focus(self) -> None:
        """Ask the running instance to surface the window it already has.

        A relaunch must not hand the running window a *new* URL: the launch
        that would supply one tears its own API down immediately afterwards,
        so the window would be sent to a dead server. Encoded as a reload with
        an empty URL, which older windows discard through their reload-URL
        guard — a no-op there rather than a broken navigation.
        """
        self._send(_RELOAD_PREFIX)

    def _send(self, payload: str) -> None:
        if _IS_WIN32:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(_SOCK_TIMEOUT)
            with sock:
                sock.connect((_TCP_LOCALHOST, self._tcp_port))
                sock.sendall(payload.encode("utf-8"))
        else:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(_SOCK_TIMEOUT)
            with sock:
                self._connect_to_sock(sock)
                sock.sendall(payload.encode("utf-8"))

    def shutdown(self) -> None:
        """Stop listening and clean up.

        Only removes the socket/port file if this controller actually bound it.
        A controller that merely probed (``probe_existing``) or lost the race
        must not delete the live instance's socket — doing so would strip the
        winner of its reload channel and leave the next launch unable to find
        it.
        """
        owns_socket = self._server_sock is not None
        self._shutdown_event.set()
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
        if self._listen_thread:
            self._listen_thread.join(timeout=0.5)
        if not owns_socket:
            return
        if _IS_WIN32:
            self._port_file.unlink(missing_ok=True)
        else:
            self._sock_path.unlink(missing_ok=True)
