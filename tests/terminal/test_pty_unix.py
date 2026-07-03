import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Unix PTY only")


def _drain_until(pty, needle: bytes, timeout: float = 5.0) -> bytes:
    buf = b""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        chunk = pty.read(4096)
        if not chunk:
            # read() is non-blocking: b"" means "nothing right now" (timeout tick)
            # while the PTY is alive, or EOF once the child has exited.
            if not pty.alive:
                break
            continue
        buf += chunk
        if needle in buf:
            return buf
    return buf


def test_unix_pty_spawns_echoes_and_kills():
    from quodeq.terminal._pty_unix import UnixPty
    pty = UnixPty(argv=["/bin/sh"])
    pty.spawn(cwd="/", cols=80, rows=24)
    assert pty.alive
    pty.write(b"echo hello-pty\n")
    out = _drain_until(pty, b"hello-pty")
    assert b"hello-pty" in out
    pty.resize(cols=100, rows=40)  # must not raise
    pty.kill()
    time.sleep(0.2)
    assert not pty.alive


def test_read_returns_empty_quickly_when_idle():
    from quodeq.terminal._pty_unix import UnixPty
    pty = UnixPty(argv=["/bin/sh"])
    pty.spawn(cwd="/", cols=80, rows=24)
    try:
        # Drain the initial prompt/banner so the shell is quiescent.
        _drain_until(pty, b"__no_such_needle__", timeout=1.0)
        # The shell is idle but alive: read() must return b"" promptly (non-blocking)
        # rather than parking in os.read forever.
        start = time.monotonic()
        chunk = pty.read(4096)
        elapsed = time.monotonic() - start
        assert chunk == b""
        assert elapsed < 1.5
        assert pty.alive
    finally:
        pty.kill()


def test_resolve_shell_returns_login_interactive_argv():
    from quodeq.terminal._pty_unix import resolve_shell
    argv = resolve_shell(env={"SHELL": "/bin/bash"})
    assert argv[0] == "/bin/bash"
    assert "-il" in argv
    # Unknown/relative shells fall back safely.
    fb = resolve_shell(env={"SHELL": "/tmp/evil"})
    assert fb[0] in ("/bin/zsh", "/bin/bash")
