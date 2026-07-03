# tests/terminal/test_manager.py
from quodeq.terminal.manager import TerminalManager


class _FakeBackend:
    def __init__(self, argv=None, env=None):
        self._alive = False
        self.written = []
        self.resized = None
        self.killed = False
        self._queue = [b"welcome\n"]
    def spawn(self, *, cwd, cols, rows): self._alive = True; self.cwd = cwd
    def read(self, max_bytes=65536): return self._queue.pop(0) if self._queue else b""
    def write(self, data): self.written.append(data)
    def resize(self, cols, rows): self.resized = (cols, rows)
    @property
    def alive(self): return self._alive
    def kill(self): self._alive = False; self.killed = True


def test_manager_spawns_once_and_records_scrollback():
    m = TerminalManager(backend_factory=_FakeBackend)
    m.ensure_session(cwd="/home/u", cols=80, rows=24)
    b1 = m._backend
    m.ensure_session(cwd="/home/u", cols=80, rows=24)  # already alive -> no respawn
    assert m._backend is b1
    assert m.read() == b"welcome\n"
    assert m.scrollback() == b"welcome\n"
    m.write(b"ls\n"); m.resize(120, 40); m.kill()
    assert b1.written == [b"ls\n"] and b1.resized == (120, 40) and not m.alive


def test_respawn_kills_stale_backend_and_replaces_it():
    m = TerminalManager(backend_factory=_FakeBackend)
    m.ensure_session(cwd="/home/u", cols=80, rows=24)
    old = m._backend
    old._alive = False  # shell exited on its own; nothing called kill()
    m.ensure_session(cwd="/home/u", cols=80, rows=24)  # reconnect -> respawn
    assert old.killed is True          # stale backend's fd was closed
    assert m._backend is not old       # a fresh backend replaced it
    assert m._backend.alive is True


def test_scrollback_is_bounded():
    m = TerminalManager(backend_factory=_FakeBackend)
    m.ensure_session(cwd="/", cols=80, rows=24)
    m._append_scrollback(b"x" * (TerminalManager.MAX_SCROLLBACK + 5000))
    assert len(m.scrollback()) <= TerminalManager.MAX_SCROLLBACK


def test_read_after_kill_returns_empty_not_crash():
    m = TerminalManager(backend_factory=_FakeBackend)
    m.ensure_session(cwd="/home/u", cols=80, rows=24)
    m.kill()
    assert m.read() == b""
    m.write(b"x")
    m.resize(80, 24)


def test_scrollback_evicts_oldest_small_chunks():
    m = TerminalManager(backend_factory=_FakeBackend)
    m.ensure_session(cwd="/", cols=80, rows=24)
    chunk_size = 1024
    num_chunks = (TerminalManager.MAX_SCROLLBACK // chunk_size) + 5
    for i in range(num_chunks):
        marker = f"chunk-{i:05d}-".encode()
        padding = b"y" * (chunk_size - len(marker))
        m._append_scrollback(marker + padding)
    data = m.scrollback()
    assert len(data) <= TerminalManager.MAX_SCROLLBACK
    assert b"chunk-00000-" not in data
    assert f"chunk-{num_chunks - 1:05d}-".encode() in data
