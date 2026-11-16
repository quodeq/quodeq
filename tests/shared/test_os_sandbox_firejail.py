"""firejail cannot empty the home as bubblewrap does, so it hides the
credential stores and Quodeq's per-launch session files by name."""
from pathlib import Path

import pytest

from quodeq.shared import os_sandbox

_STORES = (".ssh", ".aws", ".gnupg", ".config/gh", ".netrc", ".git-credentials")


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A home with the usual credential stores, on a Linux with firejail only."""
    home = tmp_path / "home"
    for store in _STORES:
        (home / store).parent.mkdir(parents=True, exist_ok=True)
        if store.startswith((".netrc", ".git-")):
            (home / store).write_text("secret\n")
        else:
            (home / store).mkdir()
    (home / ".quodeq" / "run").mkdir(parents=True)
    (home / ".quodeq" / "run" / "api-7866.session").write_text("secret\n")
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv("QUODEQ_RUN_DIR", raising=False)
    monkeypatch.setattr(os_sandbox.platform, "system", lambda: "Linux")
    monkeypatch.setattr(os_sandbox.shutil, "which",
                        lambda name: "/usr/bin/firejail" if name == "firejail" else None)
    return home


def _argv(**kwargs) -> list[str]:
    kwargs.setdefault("writable_dirs", [])
    kwargs.setdefault("writable_files", [])
    return os_sandbox.external_sandbox_prefix(**kwargs)[0]


def test_firejail_hides_the_home_credential_stores(home):
    argv = _argv(readable_home_dirs=[str(home / "repo")])
    assert [s for s in _STORES if f"--blacklist={home / s}" not in argv] == []


def test_firejail_hides_the_api_session_files(home):
    argv = _argv(writable_dirs=[str(home / ".quodeq")])
    hidden = argv.index(f"--blacklist={home / '.quodeq' / 'run'}")
    assert argv.index(f"--read-write={home / '.quodeq'}") < hidden  # later options win


def test_firejail_hides_a_run_dir_moved_by_the_environment(home, tmp_path, monkeypatch):
    moved = tmp_path / "elsewhere" / "run"
    moved.mkdir(parents=True)
    monkeypatch.setenv("QUODEQ_RUN_DIR", str(moved))
    assert f"--blacklist={moved}" in _argv()


def test_firejail_leaves_the_cli_its_own_login(home):
    (home / ".gemini").mkdir()
    (home / ".codex").mkdir()
    (home / ".codex" / "auth.json").write_text("{}")
    argv = _argv(writable_dirs=[str(home / ".gemini")],
                 writable_files=[str(home / ".codex" / "auth.json")])
    assert f"--blacklist={home / '.gemini'}" not in argv
    assert f"--blacklist={home / '.codex'}" not in argv
    assert f"--blacklist={home / '.ssh'}" in argv


def test_firejail_hides_another_cli_login(home):
    (home / ".codex").mkdir()
    (home / ".gemini").mkdir()
    argv = _argv(writable_dirs=[str(home / ".gemini")])
    assert f"--blacklist={home / '.codex'}" in argv


def test_firejail_names_only_stores_that_exist(home):
    argv = _argv()
    assert f"--blacklist={home / '.kube'}" not in argv
    assert not any(arg == "--blacklist=" for arg in argv)


def test_only_firejail_is_reported_as_leaving_home_readable(home):
    assert os_sandbox.leaves_home_readable(_argv()) is True
    assert os_sandbox.leaves_home_readable(["bwrap", "--ro-bind", "/", "/"]) is False
    assert os_sandbox.leaves_home_readable([]) is False
