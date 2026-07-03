import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows ConPTY only")


def test_windows_pty_spawns_and_echoes():
    from quodeq.terminal._pty_windows import WindowsPty, resolve_shell
    assert resolve_shell()  # resolves some shell
    pty = WindowsPty(argv=["cmd.exe"])
    pty.spawn(cwd="C:\\", cols=80, rows=24)
    assert pty.alive
    pty.write("echo hello-conpty\r\n")
    buf = ""
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        chunk = pty.read(4096).decode("utf-8", "replace")
        buf += chunk
        if "hello-conpty" in buf:
            break
    pty.resize(100, 40)
    pty.kill()
    assert "hello-conpty" in buf
