"""Store protocol for assistant session persistence."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AssistantStore(Protocol):
    """Persistence boundary for assistant sessions, messages, actions,
    event frames, and worktree rows.

    Mirrors the public surface of the concrete
    ``quodeq.data.sqlite.assistant_repository.AssistantRepository``; consumers
    (tool handlers, the orchestrator, API helpers) type against this Protocol
    so a fake store can stand in for isolated tests.
    """

    @property
    def db_path(self) -> Path:
        """Location of the backing store on disk.

        Part of the port because composition code derives sibling paths from
        it (the CLI adapter's scratch base and the MCP server's ``--db-path``
        argument).
        """
        ...

    # -- sessions -----------------------------------------------------------

    def create_session(self, *, session_id: str, provider: str,
                       model: str | None = None, project_uuid: str | None = None,
                       run_id: str | None = None,
                       project_id: str | None = None,
                       source: str = "local") -> dict:
        """Create a session row and return it."""
        ...

    def get_session(self, session_id: str) -> dict | None:
        """Return the session row, or None when unknown."""
        ...

    def set_cli_session_id(self, session_id: str, cli_session_id: str) -> None:
        """Record the CLI provider's own session id for resume."""
        ...

    def prune_sessions_older_than(self, days: int) -> int:
        """Delete sessions created more than *days* ago; return the count.

        ``days <= 0`` disables pruning (no-op). Callers must GC worktrees
        first so a pruned session's on-disk worktree is already cleaned up.
        """
        ...

    # -- messages -----------------------------------------------------------

    def add_message(self, session_id: str, role: str, content: str) -> int:
        """Append one chat message; return its row id."""
        ...

    def list_messages(self, session_id: str) -> list[dict]:
        """All messages for a session in insertion order (role, content)."""
        ...

    # -- actions ------------------------------------------------------------

    def create_action(self, *, action_id: str, session_id: str, action_type: str,
                      payload: dict, content_hash: str) -> dict:
        """Persist a drafted action and return its row (payload decoded)."""
        ...

    def get_action(self, action_id: str) -> dict | None:
        """Return the action row with ``payload`` decoded, or None."""
        ...

    def set_action_status(
        self, action_id: str, status: str, *, expected: str | None = None,
    ) -> bool:
        """Set an action's status; return whether a row was updated.

        With ``expected`` the write is a compare-and-set
        (``WHERE id=? AND status=?``), so a caller can atomically claim a
        transition. Without ``expected`` the write is unconditional.
        """
        ...

    # -- event frames -------------------------------------------------------

    def append_event(self, session_id: str, frame: dict[str, Any]) -> int:
        """Append one event frame; return its sequence number."""
        ...

    def events_after(self, session_id: str, after_seq: int,
                     limit: int = 500) -> list[tuple[int, dict]]:
        """Frames strictly after *after_seq*, ordered by sequence."""
        ...

    # -- worktrees ----------------------------------------------------------

    def upsert_worktree(self, *, session_id: str, project_id: str | None,
                        repo_root: str, path: str, branch: str) -> dict:
        """Create or refresh the session's worktree row; return it."""
        ...

    def get_worktree(self, session_id: str) -> dict | None:
        """Return the session's worktree row, or None."""
        ...

    def set_worktree_status(self, session_id: str, status: str) -> None:
        """Update the worktree row's status."""
        ...

    def list_worktrees(self, status: str, project_id: str | None = None) -> list[dict]:
        """Worktree rows with *status*, optionally scoped to a project."""
        ...

    def list_all_worktrees(self) -> list[dict]:
        """Every worktree row regardless of status (worktree GC)."""
        ...
