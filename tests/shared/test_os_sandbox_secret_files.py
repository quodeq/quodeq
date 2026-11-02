"""The OS sandbox keeps the analysed repo's credential files unreadable."""
import platform
import shutil
import subprocess
from pathlib import Path

import pytest

from quodeq.shared import os_sandbox


def test_seatbelt_denies_secret_files_after_every_read_allow():
    home = str(Path.home())
    prof = os_sandbox._seatbelt_profile(
        writable_dirs=["/w"], writable_files=[], readable_home_dirs=[f"{home}/repo"],
        unreadable_files=[f"{home}/repo/.env"])
    allow = prof.index(f"(subpath {os_sandbox._sb_quote(f'{home}/repo')})")
    deny = prof.index(f"(deny file-read-data (literal {os_sandbox._sb_quote(f'{home}/repo/.env')}))")
    assert allow < deny  # later rules win, so the repo cannot undo it


def test_bwrap_covers_secret_files_after_the_readonly_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env").write_text("TOKEN=x")
    argv = os_sandbox._bwrap_prefix([], [], readonly_dirs=[str(repo)],
                                    unreadable_files=[str(repo / ".env"), str(repo / "gone")])
    cover = argv.index(str(repo / ".env"))
    assert argv[cover - 2:cover] == ["--ro-bind", "/dev/null"]
    assert argv.index(str(repo)) < cover
    assert str(repo / "gone") not in argv  # bwrap cannot mount over a missing file


def test_firejail_blacklists_secret_files(monkeypatch):
    monkeypatch.setattr(os_sandbox.platform, "system", lambda: "Linux")
    monkeypatch.setattr(os_sandbox.shutil, "which", lambda b: "/usr/bin/firejail" if b == "firejail" else None)
    argv, _ = os_sandbox.external_sandbox_prefix(
        writable_dirs=[], writable_files=[], unreadable_files=["/r/.env"])
    assert "--blacklist=/r/.env" in argv


@pytest.mark.skipif(platform.system() != "Darwin" or not shutil.which("sandbox-exec"),
                    reason="needs macOS sandbox-exec")
def test_seatbelt_really_blocks_the_secret_file_and_nothing_else(tmp_path):
    (tmp_path / ".env").write_text("TOKEN=x\n")
    (tmp_path / "app.py").write_text("print(1)\n")
    prefix, cleanup = os_sandbox.external_sandbox_prefix(
        writable_dirs=[], writable_files=[], unreadable_files=[str((tmp_path / ".env").resolve())])
    try:
        def cat(name):
            return subprocess.run([*prefix, "cat", str(tmp_path / name)],
                                  capture_output=True, text=True, timeout=30, check=False)
        assert cat(".env").returncode != 0
        assert cat("app.py").stdout == "print(1)\n"
    finally:
        cleanup()
