import pytest

from quodeq.assistant.tools import ToolContext, build_registry
from quodeq.data.sqlite.assistant_repository import AssistantRepository


@pytest.fixture()
def ctx(tmp_path):
    repo_root = tmp_path / "project"
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "app.py").write_text("print('hi')\n")
    (repo_root / ".env").write_text("SECRET=x\n")
    (repo_root / "logo.bin").write_bytes(b"\x00\x01\x02")
    (repo_root / ".git").mkdir()
    (repo_root / ".git" / "config").write_text("[core]\n\ttoken = secret\n")
    store = AssistantRepository(tmp_path / "assistant.db")
    store.create_session(session_id="s1", provider="ollama")
    return ToolContext(
        repository=store, session_id="s1", run_dir=None, repo_root=repo_root,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
    )


def test_read_repo_file(ctx):
    reg = build_registry(ctx)
    out = reg.dispatch("read_repo_file", {"path": "src/app.py"})
    assert out["ok"] and out["result"]["content"] == "print('hi')\n"


def test_traversal_blocked(ctx):
    reg = build_registry(ctx)
    for path in ("../outside.txt", "src/../../etc/passwd", "/etc/passwd"):
        out = reg.dispatch("read_repo_file", {"path": path})
        assert out["ok"] is False, path


def test_denylist_and_binary_blocked(ctx):
    reg = build_registry(ctx)
    assert reg.dispatch("read_repo_file", {"path": ".env"})["ok"] is False
    assert reg.dispatch("read_repo_file", {"path": "logo.bin"})["ok"] is False


def test_git_dir_blocked(ctx):
    reg = build_registry(ctx)
    assert reg.dispatch("read_repo_file", {"path": ".git/config"})["ok"] is False
    assert reg.dispatch("list_repo_dir", {"path": ".git"})["ok"] is False


def test_git_dir_blocked_case_insensitive(ctx):
    # macOS APFS is case-insensitive by default -- ".GIT/config" resolves to
    # the same file as ".git/config" on disk, so the jail must compare
    # lowercased names or a differently-cased path bypasses it.
    from quodeq.assistant.tools._registry import ToolError
    from quodeq.assistant.tools._repo_tools import _jail

    with pytest.raises(ToolError, match="inside the .git directory"):
        _jail(ctx, ".GIT/config")


def test_list_repo_dir(ctx):
    reg = build_registry(ctx)
    out = reg.dispatch("list_repo_dir", {"path": "."})
    assert "src/" in out["result"]["entries"]


def test_repo_tools_without_repo_root(ctx):
    from dataclasses import replace

    reg = build_registry(replace(ctx, repo_root=None))
    assert reg.dispatch("read_repo_file", {"path": "x"})["ok"] is False
