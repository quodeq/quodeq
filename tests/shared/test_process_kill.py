import subprocess
import sys

from quodeq.shared.process_kill import kill_proc_tree
from tests._timeouts import budget


def test_kill_proc_tree_kills_a_real_process():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                            start_new_session=(sys.platform != "win32"))
    assert proc.poll() is None
    kill_proc_tree(proc)
    proc.wait(timeout=budget(10))
    assert proc.poll() is not None


def test_kill_proc_tree_tolerates_a_fake_proc():
    class FakeProc:
        pid = None

        def __init__(self): self.killed = False
        def kill(self): self.killed = True
    fake = FakeProc()
    kill_proc_tree(fake)  # must not raise
    assert fake.killed


def test_kill_tree_on_windows_logs_a_failed_taskkill(monkeypatch, caplog):
    """kill_tree on Windows checks taskkill's result instead of dropping it."""
    import logging

    from quodeq.shared import process_kill
    from quodeq.shared.constants import PLATFORM_WIN32

    monkeypatch.setattr(process_kill.sys, "platform", PLATFORM_WIN32)
    monkeypatch.setattr(process_kill, "_taskkill_tree", lambda pid: False)
    caplog.set_level(logging.DEBUG, logger=process_kill.__name__)
    process_kill.kill_tree(4242)
    assert "taskkill did not kill tree 4242" in caplog.text
