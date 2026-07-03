# src/quodeq/terminal/manager.py
"""Owns the single embedded-terminal PTY session and its scrollback ring."""
from __future__ import annotations

import threading
from collections import deque

from quodeq.terminal.backend import PtyBackend


class TerminalManager:
    MAX_SCROLLBACK = 256 * 1024

    def __init__(self, *, backend_factory=PtyBackend):
        self._factory = backend_factory
        self._backend = None
        self._lock = threading.Lock()
        self._ring: deque[bytes] = deque()
        self._ring_size = 0

    def ensure_session(self, *, cwd: str, cols: int, rows: int) -> None:
        with self._lock:
            if self._backend is not None and self._backend.alive:
                return
            self._ring.clear()
            self._ring_size = 0
            self._backend = self._factory()
            self._backend.spawn(cwd=cwd, cols=cols, rows=rows)

    def read(self, max_bytes: int = 65536) -> bytes:
        backend = self._backend
        if backend is None:
            return b""
        data = backend.read(max_bytes)
        if data:
            self._append_scrollback(data)
        return data

    def write(self, data: bytes) -> None:
        backend = self._backend
        if backend is not None:
            backend.write(data)

    def resize(self, cols: int, rows: int) -> None:
        backend = self._backend
        if backend is not None:
            backend.resize(cols, rows)

    def scrollback(self) -> bytes:
        return b"".join(self._ring)

    def kill(self) -> None:
        with self._lock:
            if self._backend is not None:
                self._backend.kill()
                self._backend = None

    @property
    def alive(self) -> bool:
        return self._backend is not None and self._backend.alive

    def _append_scrollback(self, data: bytes) -> None:
        self._ring.append(data)
        self._ring_size += len(data)
        while self._ring_size > self.MAX_SCROLLBACK and len(self._ring) > 1:
            self._ring_size -= len(self._ring.popleft())
        if self._ring_size > self.MAX_SCROLLBACK and self._ring:
            only = self._ring.pop()
            trimmed = only[-self.MAX_SCROLLBACK:]
            self._ring.append(trimmed)
            self._ring_size = len(trimmed)
