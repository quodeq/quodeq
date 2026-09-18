"""Scripted subprocess and session builders shared by the test_cli_adapter* siblings."""
import io

from quodeq.assistant.adapters._cli import CliTurnConfig, CliTurnSession
from quodeq.data.sqlite.assistant_repository import AssistantRepository


class FakeProc:
    def __init__(self, lines, returncode=0):
        self.stdout = io.StringIO("".join(l + "\n" for l in lines))
        self.stderr = io.StringIO("")
        self.returncode = returncode
        self.killed = False

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode  # scripted proc has already exited

    def kill(self):
        self.killed = True


def _config(tmp_path):
    return CliTurnConfig(provider="claude", model="sonnet", scratch_base=tmp_path,
                         mcp_server_args=["--db-path", str(tmp_path / "a.db"),
                                          "--session-id", "s1", "--evaluators-dir", str(tmp_path),
                                          "--compiled-dir", str(tmp_path),
                                          "--dimensions-file", str(tmp_path / "d.json")],
                         db_path=tmp_path / "a.db")


def _repo(tmp_path):
    repo = AssistantRepository(tmp_path / "a.db")
    repo.create_session(session_id="s1", provider="claude", model="sonnet")
    return repo


def _session(repo, *, session_id="s1", prior_session_id=None, emit=None,
             spawn_fn=None, cancel=None):
    return CliTurnSession(session_id=session_id, prior_session_id=prior_session_id,
                          repository=repo, emit=emit or (lambda f: None),
                          spawn_fn=spawn_fn, cancel=cancel)
