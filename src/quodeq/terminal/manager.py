# src/quodeq/terminal/manager.py
"""Owns the single embedded-terminal PTY session and its scrollback ring.

The manager is also the bytes->text boundary: PTY reads chunk at arbitrary
byte offsets, so a multi-byte UTF-8 character can be split across two reads.
Decoding per chunk turned every split into replacement-char artifacts on
screen (TUIs like claude redraw ❯/─/● constantly, so splits are routine).
One incremental decoder per PTY session carries partial sequences across
reads — and across client reconnects, which a per-connection decoder in the
WS handler could not do. ``read()``/``scrollback()`` therefore return ``str``;
``write()`` stays bytes (input is encoded by the caller).
"""
from __future__ import annotations

import codecs
import threading
from collections import deque

from quodeq.terminal.backend import PtyBackend


class TerminalManager:
    MAX_SCROLLBACK = 256 * 1024  # characters

    def __init__(self, *, backend_factory=PtyBackend):
        self._factory = backend_factory
        self._backend = None
        self._lock = threading.Lock()
        self._ring: deque[str] = deque()
        self._ring_size = 0
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def ensure_session(self, *, cwd: str, cols: int, rows: int) -> None:
        with self._lock:
            if self._backend is not None and self._backend.alive:
                return
            if self._backend is not None:      # stale/dead backend -> close its fd first
                self._backend.kill()
            self._ring.clear()
            self._ring_size = 0
            # Fresh PTY = fresh byte stream; a dangling partial character from
            # the dead session must not bleed into the new one.
            self._decoder.reset()
            self._backend = self._factory()
            self._backend.spawn(cwd=cwd, cols=cols, rows=rows)

    def read(self, max_bytes: int = 65536) -> str:
        """Return decoded output, holding back a trailing partial character.

        May return "" even when bytes arrived (all of them belonged to a
        still-incomplete character); the next read completes it.
        """
        backend = self._backend
        if backend is None:
            return ""
        data = self._decoder.decode(backend.read(max_bytes))
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

    def scrollback(self) -> str:
        return "".join(self._ring)

    def kill(self) -> None:
        with self._lock:
            if self._backend is not None:
                self._backend.kill()
                self._backend = None

    @property
    def alive(self) -> bool:
        return self._backend is not None and self._backend.alive

    @property
    def pid(self) -> int | None:
        """PID of the live shell, or None. Used to read the shell's cwd so
        clickable relative paths resolve against where the user actually is."""
        backend = self._backend
        return backend.pid if backend is not None else None

    def _append_scrollback(self, data: str) -> None:
        self._ring.append(data)
        self._ring_size += len(data)
        while self._ring_size > self.MAX_SCROLLBACK and len(self._ring) > 1:
            self._ring_size -= len(self._ring.popleft())
        if self._ring_size > self.MAX_SCROLLBACK and self._ring:
            only = self._ring.pop()
            trimmed = only[-self.MAX_SCROLLBACK:]
            self._ring.append(trimmed)
            self._ring_size = len(trimmed)
