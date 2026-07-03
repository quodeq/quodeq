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
            break
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


def test_resolve_shell_returns_login_interactive_argv():
    from quodeq.terminal._pty_unix import resolve_shell
    argv = resolve_shell(env={"SHELL": "/bin/bash"})
    assert argv[0] == "/bin/bash"
    assert "-il" in argv
    # Unknown/relative shells fall back safely.
    fb = resolve_shell(env={"SHELL": "/tmp/evil"})
    assert fb[0] in ("/bin/zsh", "/bin/bash")
