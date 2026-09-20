"""The git CLI adapter is the single place that shells out to git.

services/_fs_scan, services/project_registration, shared/_repo and
analysis/subagents/_git_scoring used to run subprocess directly. The
process execution now lives in ``data/git_cli.py``; the callers keep only
their domain logic (and shared keeps the pure URL normalizer).
"""
from __future__ import annotations

import subprocess as sp
from pathlib import Path


def _init_repo(tmp_path: Path) -> Path:
    sp.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    return tmp_path


def _commit(repo: Path, name: str = "f.txt") -> None:
    (repo / name).write_text("x")
    sp.run(["git", "-C", str(repo), "add", "."], check=True)
    sp.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "-m", "c"],
        check=True,
    )


class TestRunGit:
    def test_returns_stdout_on_success(self, tmp_path):
        from quodeq.data.git_cli import run_git

        repo = _init_repo(tmp_path)
        out = run_git(["rev-parse", "--is-inside-work-tree"], cwd=repo)
        assert out is not None and out.strip() == "true"

    def test_returns_none_outside_a_repo(self, tmp_path):
        from quodeq.data.git_cli import run_git

        assert run_git(["rev-parse", "--is-inside-work-tree"], cwd=tmp_path) is None


def _raise_missing_git(*_args, **_kwargs):
    raise FileNotFoundError("git")


class TestListTrackedFiles:
    def test_lists_committed_and_staged_paths(self, tmp_path):
        from quodeq.data.git_cli import list_tracked_files

        repo = _init_repo(tmp_path)
        _commit(repo, "a.txt")
        (repo / "staged.txt").write_text("y")
        sp.run(["git", "-C", str(repo), "add", "staged.txt"], check=True)
        (repo / "loose.txt").write_text("z")

        assert list_tracked_files(repo) == {
            (repo / "a.txt").resolve(), (repo / "staged.txt").resolve(),
        }

    def test_subtree_listing_is_absolute(self, tmp_path):
        """Run at a subdirectory, git lists only that subtree and reports
        paths relative to it; the helper rebases them onto the scan dir."""
        from quodeq.data.git_cli import list_tracked_files

        repo = _init_repo(tmp_path)
        (repo / "pkg").mkdir()
        (repo / "pkg" / "mod.py").write_text("x")
        (repo / "top.py").write_text("x")
        sp.run(["git", "-C", str(repo), "add", "-A"], check=True)

        assert list_tracked_files(repo / "pkg") == {(repo / "pkg" / "mod.py").resolve()}

    def test_subtree_with_nothing_tracked_filters_everything(self, tmp_path):
        """A gitignored or simply untracked subtree is not a missing answer.

        `ls-files` runs with -C, so it only ever lists the subtree it was
        pointed at. An empty listing there, in a repository that tracks
        files elsewhere, means nothing under that root belongs to the
        codebase: the right answer is an empty set, not the unfiltered
        working tree.
        """
        from quodeq.data.git_cli import list_tracked_files

        repo = _init_repo(tmp_path)
        _commit(repo, "tracked.py")
        vendor = repo / "vendor"
        vendor.mkdir()
        (vendor / "bundled.py").write_text("x = 1\n")

        assert list_tracked_files(vendor) == set()

    def test_empty_index_does_not_filter(self, tmp_path, caplog):
        """A repo before its first `git add` has no baseline to filter on.

        Returning an empty set would score zero files, which is never a
        useful answer, so an empty index falls back to the unfiltered
        working tree and says why.
        """
        import logging

        from quodeq.data.git_cli import list_tracked_files

        repo = _init_repo(tmp_path)
        with caplog.at_level(logging.INFO, logger="quodeq.data.git_cli"):
            assert list_tracked_files(repo) is None
        assert "Nothing tracked" in caplog.text

    def test_both_unicode_spellings_of_a_name_are_tracked(self, tmp_path):
        """git keeps the bytes it was given; a filesystem may compose a name
        differently, and a byte-exact miss would drop a real source file."""
        import unicodedata

        from quodeq.data.git_cli import list_tracked_files

        repo = _init_repo(tmp_path)
        name = unicodedata.normalize("NFC", "café.py")
        (repo / name).write_text("x = 1\n")
        sp.run(["git", "-C", str(repo), "add", "-A"], check=True)

        tracked = list_tracked_files(repo)
        assert tracked is not None
        for form in ("NFC", "NFD"):
            assert (repo / unicodedata.normalize(form, name)).resolve() in tracked

    def test_non_repo_returns_none(self, tmp_path):
        from quodeq.data.git_cli import list_tracked_files

        assert list_tracked_files(tmp_path) is None

    def test_missing_git_binary_returns_none(self, tmp_path, monkeypatch):
        from quodeq.data import git_cli

        repo = _init_repo(tmp_path)
        _commit(repo)
        monkeypatch.setattr(git_cli.subprocess, "run", _raise_missing_git)
        assert git_cli.list_tracked_files(repo) is None

    def test_undecodable_path_returns_none(self, tmp_path, monkeypatch):
        from quodeq.data import git_cli

        def _boom(*_args, **_kwargs):
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

        monkeypatch.setattr(git_cli, "run_git", _boom)
        assert git_cli.list_tracked_files(tmp_path) is None


class TestListBranches:
    def test_lists_local_branches(self, tmp_path):
        from quodeq.data.git_cli import list_branches

        repo = _init_repo(tmp_path)
        _commit(repo)
        assert list_branches(repo) == ["main"]

    def test_non_repo_returns_empty(self, tmp_path):
        from quodeq.data.git_cli import list_branches

        assert list_branches(tmp_path) == []


class TestRemoteOrigin:
    def test_raw_url(self, tmp_path):
        from quodeq.data.git_cli import remote_origin_url_raw

        repo = _init_repo(tmp_path)
        sp.run(
            ["git", "-C", str(repo), "remote", "add", "origin",
             "https://github.com/x/y.git"],
            check=True,
        )
        assert remote_origin_url_raw(repo) == "https://github.com/x/y.git"

    def test_none_without_remote(self, tmp_path):
        from quodeq.data.git_cli import remote_origin_url_raw

        assert remote_origin_url_raw(_init_repo(tmp_path)) is None

    def test_normalized_remote_url(self, tmp_path):
        from quodeq.data.git_cli import git_remote_url

        repo = _init_repo(tmp_path)
        sp.run(
            ["git", "-C", str(repo), "remote", "add", "origin",
             "git@github.com:quodeq/quodeq.git"],
            check=True,
        )
        assert git_remote_url(str(repo)) == "github.com/quodeq/quodeq"

    def test_normalized_none_for_non_repo(self, tmp_path):
        from quodeq.data.git_cli import git_remote_url

        assert git_remote_url(str(tmp_path)) is None


class TestStreamLogNames:
    def test_yields_log_lines(self, tmp_path):
        from quodeq.data.git_cli import stream_log_names

        repo = _init_repo(tmp_path)
        _commit(repo, "a.txt")
        lines = list(stream_log_names(repo, months=1))
        assert any("a.txt" in line for line in lines)

    def test_non_repo_yields_nothing(self, tmp_path):
        from quodeq.data.git_cli import stream_log_names

        assert list(stream_log_names(tmp_path, months=3)) == []


def test_callers_carry_no_subprocess_dependency():
    """Process execution is an adapter-layer detail: none of the former
    call sites may import subprocess at runtime."""
    import quodeq.analysis.subagents._git_scoring as git_scoring
    import quodeq.services._fs_scan as fs_scan
    import quodeq.services.project_registration as project_registration
    import quodeq.shared.repo as repo

    for mod in (fs_scan, project_registration, repo, git_scoring):
        assert "subprocess" not in vars(mod), mod.__name__
