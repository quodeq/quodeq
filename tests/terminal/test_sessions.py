"""TerminalSessionRegistry: creation, naming, cap, kill semantics, isolation."""

from quodeq.terminal.sessions import TerminalSessionRegistry, shell_name


class _FakeManager:
    def __init__(self):
        self.killed = False
        self._alive = True
        self.written = b""

    def write(self, data):
        self.written += data

    def kill(self):
        self.killed = True
        self._alive = False

    @property
    def alive(self):
        return self._alive

    @property
    def pid(self):
        return None


def _registry():
    return TerminalSessionRegistry(manager_factory=_FakeManager)


def test_create_assigns_unique_ids_and_sequential_names():
    reg = _registry()
    a = reg.create()
    b = reg.create()
    assert a.id != b.id
    assert a.name.endswith("· 1") and b.name.endswith("· 2")


def test_closing_frees_the_ordinal_for_reuse():
    # Like real terminal tabs: close "zsh · 2" and the next new session is
    # "zsh · 2" again — numbers stay within 1..MAX_SESSIONS forever.
    reg = _registry()
    reg.create()
    b = reg.create()
    c = reg.create()
    reg.kill(b.id)
    d = reg.create()
    assert d.name.endswith("· 2")
    assert c.name.endswith("· 3")
    # next one takes the next free slot, not a duplicate
    assert reg.create().name.endswith("· 4")


def test_ordinals_never_exceed_the_cap():
    reg = _registry()
    for _ in range(3):
        sessions = [reg.create() for _ in range(TerminalSessionRegistry.MAX_SESSIONS)]
        assert all(
            1 <= s.ordinal <= TerminalSessionRegistry.MAX_SESSIONS for s in sessions
        )
        reg.kill_all()


def test_create_returns_none_at_cap():
    reg = _registry()
    for _ in range(TerminalSessionRegistry.MAX_SESSIONS):
        assert reg.create() is not None
    assert reg.create() is None
    # killing one frees a slot
    victim = reg.list()[0]["id"]
    assert reg.kill(victim)
    assert reg.create() is not None


def test_list_reflects_sessions():
    reg = _registry()
    assert reg.list() == []
    a = reg.create()
    listed = reg.list()
    assert len(listed) == 1
    item = listed[0]
    assert item["id"] == a.id and item["name"] == a.name
    assert item["alive"] is True and item["createdAt"] == a.created_at


def test_kill_removes_and_kills_only_target():
    reg = _registry()
    a = reg.create()
    b = reg.create()
    assert reg.kill(a.id) is True
    assert a.manager.killed and not b.manager.killed
    assert reg.get(a.id) is None and reg.get(b.id) is b


def test_kill_unknown_returns_false():
    assert _registry().kill("nope") is False


def test_kill_all_empties_registry():
    reg = _registry()
    sessions = [reg.create() for _ in range(3)]
    reg.kill_all()
    assert reg.list() == []
    assert all(s.manager.killed for s in sessions)
    assert reg.any_alive is False


def test_sessions_have_independent_managers_and_locks():
    reg = _registry()
    a = reg.create()
    b = reg.create()
    assert a.manager is not b.manager
    a.manager.write(b"only-a")
    assert b.manager.written == b""
    # A's held connection lock must not block B's.
    assert a.conn_lock.acquire(blocking=False)
    try:
        assert b.conn_lock.acquire(blocking=False)
        b.conn_lock.release()
    finally:
        a.conn_lock.release()


def test_get_or_create_default_reuses_existing():
    reg = _registry()
    first = reg.get_or_create_default()
    assert reg.get_or_create_default() is first
    assert len(reg.list()) == 1


def test_pid_for_falls_back_to_first_alive():
    reg = _registry()
    assert reg.pid_for(None) is None       # empty registry
    a = reg.create()
    assert reg.pid_for(a.id) == a.manager.pid
    assert reg.pid_for("unknown") is None  # explicit unknown id: no fallback


def test_shell_name_is_plain_basename():
    name = shell_name()
    assert name and "/" not in name and "\\" not in name
