import argparse

from quodeq.assistant.mcp.server import _build_registry_from_args


def _ns(tmp_path, **overrides):
    base = dict(db_path=str(tmp_path / "a.db"), session_id="s1", run_dir="",
                repo_root="", evaluators_dir=str(tmp_path / "e"),
                compiled_dir=str(tmp_path / "c"),
                dimensions_file=str(tmp_path / "d.json"), project_id="",
                reports_dir=str(tmp_path / "r"), enable_write=False,
                worktree_dir="")
    base.update(overrides)
    return argparse.Namespace(**base)


def test_mcp_registry_without_write_flag(tmp_path):
    names = _build_registry_from_args(_ns(tmp_path)).names()
    assert "edit_repo_file" not in names


def test_mcp_registry_with_write_flag(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    ns = _ns(tmp_path, enable_write=True, worktree_dir=str(wt))
    names = _build_registry_from_args(ns).names()
    assert {"edit_repo_file", "write_repo_file", "delete_repo_file",
            "get_worktree_diff"} <= set(names)


def test_mcp_registry_enable_write_without_worktree(tmp_path):
    # --enable-write without a worktree must stay read-only: write tools are
    # jailed to the worktree, so no worktree means no write surface at all.
    ns = _ns(tmp_path, enable_write=True, worktree_dir="")
    names = _build_registry_from_args(ns).names()
    assert "edit_repo_file" not in names
    assert "write_repo_file" not in names
