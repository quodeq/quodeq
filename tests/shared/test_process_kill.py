import subprocess
import sys
import time

from quodeq.shared._process_kill import kill_proc_tree


def test_kill_proc_tree_kills_a_real_process():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                            start_new_session=(sys.platform != "win32"))
    assert proc.poll() is None
    kill_proc_tree(proc)
    proc.wait(timeout=10)
    assert proc.poll() is not None


def test_kill_proc_tree_tolerates_a_fake_proc():
    class FakeProc:
        pid = None
        def __init__(self): self.killed = False
        def kill(self): self.killed = True
    fake = FakeProc()
    kill_proc_tree(fake)  # must not raise
    assert fake.killed
