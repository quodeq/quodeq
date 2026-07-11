import pytest

from quodeq.assistant.tools import ToolContext, ToolRegistry, build_registry
from quodeq.assistant.tools._write_tools import register_write_tools
from quodeq.assistant.worktree import WorktreeManager, _run
from quodeq.data.sqlite.assistant_repository import AssistantRepository


@pytest.fixture()
def wt_ctx(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "-C", str(repo), "init", "-q", "-b", "main"])
    _run(["git", "-C", str(repo), "config", "core.autocrlf", "false"])
    _run(["git", "-C", str(repo), "config", "user.name", "T"])
    _run(["git", "-C", str(repo), "config", "user.email", "t@example.com"])
    (repo / "app.py").write_bytes(b"a = 1\nb = 2\nb = 2\n")
    _run(["git", "-C", str(repo), "add", "-A"])
    _run(["git", "-C", str(repo), "commit", "-q", "-m", "init"])
    manager = WorktreeManager.for_session(repo, "proj", "abcdef1234567890",
                                          base=tmp_path / "wts")
    manager.create()
    store = AssistantRepository(tmp_path / "assistant.db")
    store.create_session(session_id="s1", provider="ollama")
    return ToolContext(
        repository=store, session_id="s1", run_dir=None, repo_root=repo,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json", worktree_dir=manager.path)


def _registry(ctx):
    reg = ToolRegistry()
    register_write_tools(reg, ctx)
    return reg


def test_write_tools_never_in_build_registry(wt_ctx):
    names = build_registry(wt_ctx).names()
    for name in ("edit_repo_file", "write_repo_file", "delete_repo_file",
                 "get_worktree_diff"):
        assert name not in names


def test_edit_unique_match(wt_ctx):
    reg = _registry(wt_ctx)
    out = reg.dispatch("edit_repo_file", {"path": "app.py", "old_string": "a = 1",
                                          "new_string": "a = 9"})
    assert out["ok"]
    assert (wt_ctx.worktree_dir / "app.py").read_bytes() == b"a = 9\nb = 2\nb = 2\n"
    # the USER's repo copy is untouched
    assert (wt_ctx.repo_root / "app.py").read_bytes() == b"a = 1\nb = 2\nb = 2\n"


def test_edit_preserves_crlf_line_endings(wt_ctx):
    # A CRLF file (a Windows user's repo) must keep its exact line endings on
    # edit. write_text would translate "\n" to the platform newline on Windows
    # and double every "\r\n" into "\r\r\n"; write_bytes preserves the file.
    (wt_ctx.worktree_dir / "crlf.py").write_bytes(b"a = 1\r\nb = 2\r\n")
    reg = _registry(wt_ctx)
    out = reg.dispatch("edit_repo_file", {"path": "crlf.py", "old_string": "a = 1",
                                          "new_string": "a = 9"})
    assert out["ok"]
    assert (wt_ctx.worktree_dir / "crlf.py").read_bytes() == b"a = 9\r\nb = 2\r\n"


def test_edit_rejects_ambiguous_and_missing(wt_ctx):
    reg = _registry(wt_ctx)
    assert reg.dispatch("edit_repo_file", {"path": "app.py", "old_string": "b = 2",
                                           "new_string": "x"})["ok"] is False
    assert reg.dispatch("edit_repo_file", {"path": "app.py", "old_string": "zzz",
                                           "new_string": "x"})["ok"] is False


def test_write_new_file_and_jail(wt_ctx):
    reg = _registry(wt_ctx)
    assert reg.dispatch("write_repo_file", {"path": "pkg/new.py",
                                            "content": "x = 1\n"})["ok"]
    assert (wt_ctx.worktree_dir / "pkg" / "new.py").is_file()
    for path in ("../escape.py", "/etc/pwn", ".env"):
        assert reg.dispatch("write_repo_file",
                            {"path": path, "content": "x"})["ok"] is False, path


def test_workflow_write_denied(wt_ctx):
    reg = _registry(wt_ctx)
    out = reg.dispatch("write_repo_file", {"path": ".github/workflows/ci.yml",
                                           "content": "on: push\n"})
    assert out["ok"] is False and "workflow" in out["error"]


def test_delete_file(wt_ctx):
    reg = _registry(wt_ctx)
    assert reg.dispatch("delete_repo_file", {"path": "app.py"})["ok"]
    assert not (wt_ctx.worktree_dir / "app.py").exists()


def test_get_worktree_diff_reports_changes(wt_ctx):
    reg = _registry(wt_ctx)
    reg.dispatch("write_repo_file", {"path": "new.py", "content": "x = 1\n"})
    out = reg.dispatch("get_worktree_diff", {})
    assert out["ok"] and "new.py" in out["result"]["diff"]
    assert out["result"]["stats"][0]["file"] == "new.py"


def test_write_tools_error_without_worktree(wt_ctx):
    from dataclasses import replace

    reg = ToolRegistry()
    register_write_tools(reg, replace(wt_ctx, worktree_dir=None))
    assert reg.dispatch("write_repo_file", {"path": "x", "content": ""})["ok"] is False


def test_workflow_write_denied_case_insensitive(wt_ctx):
    reg = _registry(wt_ctx)
    for path in (".GitHub/Workflows/evil.yml", ".github/Workflows/evil.yml"):
        out = reg.dispatch("write_repo_file", {"path": path, "content": "on: push\n"})
        assert out["ok"] is False and "workflow" in out["error"], path
    assert not (wt_ctx.worktree_dir / ".github" / "workflows").exists()


def test_edit_rejects_non_utf8_and_binary(wt_ctx):
    (wt_ctx.worktree_dir / "latin.py").write_bytes(b"# caf\xe9\nTARGET = 1\n")
    (wt_ctx.worktree_dir / "blob.bin").write_bytes(b"\x00\x01TARGET")
    reg = _registry(wt_ctx)
    out = reg.dispatch("edit_repo_file", {"path": "latin.py", "old_string": "TARGET = 1",
                                          "new_string": "TARGET = 9"})
    assert out["ok"] is False
    assert (wt_ctx.worktree_dir / "latin.py").read_bytes() == b"# caf\xe9\nTARGET = 1\n"
    out = reg.dispatch("edit_repo_file", {"path": "blob.bin", "old_string": "TARGET",
                                          "new_string": "X"})
    assert out["ok"] is False


def test_edit_result_size_capped(wt_ctx):
    reg = _registry(wt_ctx)
    out = reg.dispatch("edit_repo_file", {"path": "app.py", "old_string": "a = 1",
                                          "new_string": "x" * 70_000})
    assert out["ok"] is False and "exceed" in out["error"]
