"""ToolContext and the turn plumbing are typed against AssistantStore.

The port (``data/ports/assistant.py``) exists so tool handlers and the
orchestrator can be driven by a fake store instead of the concrete SQLite
repository. These tests pin the seam: the concrete class satisfies the
Protocol, a plain in-memory fake does too, and the fake slots into
ToolContext without touching SQLite.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.assistant.tools import ToolContext
from quodeq.data.ports.assistant import AssistantStore
from quodeq.data.sqlite.assistant_repository import AssistantRepository


class FakeAssistantStore:
    """Minimal in-memory stand-in satisfying the AssistantStore Protocol."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self.sessions: dict[str, dict] = {}
        self.messages: list[dict] = []
        self.actions: dict[str, dict] = {}
        self.events: list[tuple[int, str, dict]] = []
        self.worktrees: dict[str, dict] = {}

    @property
    def db_path(self) -> Path:
        return self._db_path

    def create_session(self, *, session_id: str, provider: str,
                       model: str | None = None, project_uuid: str | None = None,
                       run_id: str | None = None,
                       project_id: str | None = None,
                       source: str = "local") -> dict:
        row = {"id": session_id, "provider": provider, "model": model,
               "project_uuid": project_uuid, "run_id": run_id,
               "project_id": project_id, "source": source,
               "cli_session_id": None}
        self.sessions[session_id] = row
        return row

    def get_session(self, session_id: str) -> dict | None:
        return self.sessions.get(session_id)

    def set_cli_session_id(self, session_id: str, cli_session_id: str) -> None:
        self.sessions[session_id]["cli_session_id"] = cli_session_id

    def prune_sessions_older_than(self, days: int) -> int:
        return 0

    def add_message(self, session_id: str, role: str, content: str) -> int:
        self.messages.append({"session_id": session_id, "role": role,
                              "content": content})
        return len(self.messages)

    def list_messages(self, session_id: str) -> list[dict]:
        return [{"role": m["role"], "content": m["content"]}
                for m in self.messages if m["session_id"] == session_id]

    def create_action(self, *, action_id: str, session_id: str, action_type: str,
                      payload: dict, content_hash: str) -> dict:
        row = {"id": action_id, "session_id": session_id,
               "action_type": action_type, "payload": payload,
               "content_hash": content_hash, "status": "drafted"}
        self.actions[action_id] = row
        return row

    def get_action(self, action_id: str) -> dict | None:
        return self.actions.get(action_id)

    def set_action_status(
        self, action_id: str, status: str, *, expected: str | None = None,
    ) -> bool:
        row = self.actions.get(action_id)
        if row is None or (expected is not None and row["status"] != expected):
            return False
        row["status"] = status
        return True

    def append_event(self, session_id: str, frame: dict[str, Any]) -> int:
        seq = len(self.events) + 1
        self.events.append((seq, session_id, frame))
        return seq

    def events_after(self, session_id: str, after_seq: int,
                     limit: int = 500) -> list[tuple[int, dict]]:
        rows = [(seq, frame) for seq, sid, frame in self.events
                if sid == session_id and seq > after_seq]
        return rows[:limit]

    def upsert_worktree(self, *, session_id: str, project_id: str | None,
                        repo_root: str, path: str, branch: str) -> dict:
        row = {"session_id": session_id, "project_id": project_id,
               "repo_root": repo_root, "path": path, "branch": branch,
               "status": "active"}
        self.worktrees[session_id] = row
        return row

    def get_worktree(self, session_id: str) -> dict | None:
        return self.worktrees.get(session_id)

    def set_worktree_status(self, session_id: str, status: str) -> None:
        self.worktrees[session_id]["status"] = status

    def list_worktrees(self, status: str, project_id: str | None = None) -> list[dict]:
        rows = [r for r in self.worktrees.values() if r["status"] == status]
        if project_id is not None:
            rows = [r for r in rows if r["project_id"] == project_id]
        return rows

    def list_all_worktrees(self) -> list[dict]:
        return list(self.worktrees.values())


def _ctx(tmp_path, repository) -> ToolContext:
    return ToolContext(
        repository=repository, session_id="s1", run_dir=None, repo_root=None,
        evaluators_dir=tmp_path / "evaluators", compiled_dir=tmp_path / "compiled",
        dimensions_file=tmp_path / "dimensions.json",
    )


def test_concrete_repository_satisfies_protocol(tmp_path):
    repo = AssistantRepository(tmp_path / "assistant.db")
    assert isinstance(repo, AssistantStore)


def test_fake_store_satisfies_protocol(tmp_path):
    fake = FakeAssistantStore(tmp_path / "fake.db")
    assert isinstance(fake, AssistantStore)


def test_arbitrary_object_does_not_satisfy_protocol():
    assert not isinstance(object(), AssistantStore)


def test_fake_store_slots_into_tool_context(tmp_path):
    fake = FakeAssistantStore(tmp_path / "fake.db")
    ctx = _ctx(tmp_path, fake)

    assert ctx.repository is fake
    # The attribute consumers actually use beyond methods (orchestrator's
    # CliTurnConfig scratch_base / db_path, MCP --db-path argv).
    assert ctx.repository.db_path == tmp_path / "fake.db"

    ctx.repository.create_session(session_id="s1", provider="ollama")
    ctx.repository.add_message("s1", "user", "hi")
    assert ctx.repository.list_messages("s1") == [{"role": "user", "content": "hi"}]
    seq = ctx.repository.append_event("s1", {"type": "done"})
    assert ctx.repository.events_after("s1", 0) == [(seq, {"type": "done"})]
