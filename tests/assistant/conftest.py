"""Shared fixtures for tests/assistant."""
import pytest

from quodeq.assistant.tools import ToolContext
from quodeq.data.sqlite.assistant_repository import AssistantRepository


@pytest.fixture()
def setup(tmp_path):
    """(repository, ToolContext) for session "s1" with no run or repo scope.

    Shared by the test_orchestrator* siblings.
    """
    repo = AssistantRepository(tmp_path / "assistant.db")
    repo.create_session(session_id="s1", provider="ollama", model="m")
    ctx = ToolContext(
        repository=repo, session_id="s1", run_dir=None, repo_root=None,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
    )
    return repo, ctx
