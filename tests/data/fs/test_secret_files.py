"""Finding a repo's credential files: all of them for the sandbox, tracked ones for the check."""
import os
import subprocess

import pytest

from quodeq.data.fs.secret_files import find_secret_files, read_tracked_secret_files


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                   env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull})


def test_finds_secret_files_at_any_depth_but_not_in_dependencies(tmp_path):
    (tmp_path / "svc").mkdir()
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    for rel in (".env", "svc/.env.local", "svc/tls.key", "node_modules/pkg/.env",
                ".env.example", "app.py"):
        (tmp_path / rel).write_text("x")
    found = {p.relative_to(tmp_path).as_posix() for p in find_secret_files(tmp_path)}
    assert found == {".env", "svc/.env.local", "svc/tls.key"}


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_a_symlinked_secret_file_is_listed_with_its_target(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env").symlink_to(outside)
    assert set(find_secret_files(repo)) == {repo / ".env", outside.resolve()}


def test_the_walk_stops_at_the_limit(tmp_path):
    for i in range(5):
        (tmp_path / f"k{i}.pem").write_text("x")
    assert len(find_secret_files(tmp_path, limit=3)) == 3


def test_reads_only_tracked_secret_files(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text(".env.local\n")
    (tmp_path / ".env").write_text("TOKEN=abc\n")
    (tmp_path / ".env.local").write_text("TOKEN=local\n")
    (tmp_path / "app.py").write_text("print(1)\n")
    _git(tmp_path, "add", ".")
    assert read_tracked_secret_files(tmp_path) == [(".env", "assignments", "TOKEN=abc\n")]


def test_outside_git_nothing_is_read(tmp_path):
    (tmp_path / ".env").write_text("TOKEN=abc\n")
    assert read_tracked_secret_files(tmp_path) == []
