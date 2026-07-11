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
    assert m.read() == "welcome\n"
    assert m.scrollback() == "welcome\n"
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
    m._append_scrollback("x" * (TerminalManager.MAX_SCROLLBACK + 5000))
    assert len(m.scrollback()) <= TerminalManager.MAX_SCROLLBACK


def test_read_after_kill_returns_empty_not_crash():
    m = TerminalManager(backend_factory=_FakeBackend)
    m.ensure_session(cwd="/home/u", cols=80, rows=24)
    m.kill()
    assert m.read() == ""
    m.write(b"x")
    m.resize(80, 24)


def test_scrollback_evicts_oldest_small_chunks():
    m = TerminalManager(backend_factory=_FakeBackend)
    m.ensure_session(cwd="/", cols=80, rows=24)
    chunk_size = 1024
    num_chunks = (TerminalManager.MAX_SCROLLBACK // chunk_size) + 5
    for i in range(num_chunks):
        marker = f"chunk-{i:05d}-"
        padding = "y" * (chunk_size - len(marker))
        m._append_scrollback(marker + padding)
    data = m.scrollback()
    assert len(data) <= TerminalManager.MAX_SCROLLBACK
    assert "chunk-00000-" not in data
    assert f"chunk-{num_chunks - 1:05d}-" in data


def test_read_reassembles_utf8_char_split_across_chunks():
    # PTY reads chunk at arbitrary byte offsets; a multi-byte character
    # ('❯' = e2 9d af, the glyph TUIs use for selection markers) split
    # across two reads must NOT decode to replacement chars ('�') --
    # that was the "artifacts during claude menus" bug. The partial tail is
    # held back and completed by the next read.
    m = TerminalManager(backend_factory=_FakeBackend)
    m.ensure_session(cwd="/", cols=80, rows=24)
    m._backend._queue = [b"ok \xe2\x9d", b"\xaf done"]
    first = m.read()
    second = m.read()
    assert "�" not in first + second
    assert first + second == "ok ❯ done"


def test_scrollback_replays_clean_text_after_split_reads():
    m = TerminalManager(backend_factory=_FakeBackend)
    m.ensure_session(cwd="/", cols=80, rows=24)
    m._backend._queue = [b"\xe2\x9d", b"\xaf", b"\xe2\x96", b"\x8c"]
    for _ in range(4):  # a partial-char read returns "" — keep draining
        m.read()
    assert m.scrollback() == "❯▌"


def test_decoder_state_resets_on_respawn():
    # A dangling partial char from a dead session must not corrupt the first
    # bytes of the next session's stream.
    m = TerminalManager(backend_factory=_FakeBackend)
    m.ensure_session(cwd="/", cols=80, rows=24)
    m._backend._queue = [b"\xe2\x9d"]  # partial char, never completed
    m.read()
    m._backend._alive = False
    m.ensure_session(cwd="/", cols=80, rows=24)  # respawn
    m._backend._queue = [b"fresh"]
    assert m.read() == "fresh"
