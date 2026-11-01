"""Live checks that a sandbox a machine reports as working really confines.

Runs only with QUODEQ_SANDBOX_LIVE=1 (the Sandbox Live workflow, on Linux,
macOS and Windows runners). A machine without a given sandbox skips that
check with the reason, which is the information the job exists to surface;
a sandbox that is chosen but leaks fails it.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from quodeq.analysis import codex_sandbox
from quodeq.shared import os_sandbox

pytestmark = pytest.mark.skipif(
    os.environ.get("QUODEQ_SANDBOX_LIVE") != "1", reason="live sandbox checks run in CI only")

_WINDOWS = platform.system() == "Windows"
_SECRET = "quodeq-sandbox-live-secret"
_URL = "https://example.com/"


@pytest.fixture
def layout(tmp_path):
    """A repo outside home, a writable out dir, and a secret under home."""
    repo, out = tmp_path / "repo", tmp_path / "out"
    repo.mkdir()
    out.mkdir()
    (repo / "app.py").write_text("x = 1\n", encoding="utf-8")
    secret = Path.home() / f".{_SECRET}.txt"
    secret.write_text(_SECRET, encoding="utf-8")
    yield repo, out, secret
    secret.unlink(missing_ok=True)


def _ok(argv: list[str], cwd: Path) -> bool:
    return subprocess.run(argv, cwd=cwd, capture_output=True, timeout=60, check=False).returncode == 0


def _shell(script: str) -> list[str]:
    return ["cmd.exe", "/c", script] if _WINDOWS else ["/bin/sh", "-c", script]


def _cat(path: Path) -> str:
    return f'type "{path}"' if _WINDOWS else f'cat "{path}"'


def _touch(path: Path) -> str:
    return f'echo x > "{path}"' if _WINDOWS else f'touch "{path}"'


def _fetch() -> str:
    return f"curl.exe -sf -m 10 -o NUL {_URL}" if _WINDOWS else f"curl -sf -m 10 -o /dev/null {_URL}"


def test_os_sandbox_confines_what_it_runs(layout):
    repo, out, secret = layout
    try:
        prefix, cleanup = os_sandbox.external_sandbox_prefix(
            writable_dirs=[str(out)], writable_files=[],
            readable_home_dirs=[str(repo), *(str(d) for d in os_sandbox.runtime_readable_dirs())],
            readonly_dirs=[str(repo)])
    except os_sandbox.SandboxUnavailable as exc:
        pytest.skip(f"no OS sandbox here, scans fall back: {exc}")
    try:
        assert _ok([*prefix, *_shell(_cat(repo / "app.py"))], repo), "repo must stay readable"
        assert _ok([*prefix, *_shell(_touch(out / "ok.txt"))], repo), "out dir must stay writable"
        assert not _ok([*prefix, *_shell(_touch(repo / "pwned.txt"))], repo), "repo write leaked"
        if prefix[0] != "firejail":  # firejail confines writes only
            assert not _ok([*prefix, *_shell(_cat(secret))], repo), "home read leaked"
    finally:
        cleanup()


@pytest.fixture
def codex(tmp_path):
    binary = shutil.which("codex")
    if binary is None:
        pytest.skip("codex is not installed")
    # Under home like Quodeq's real one: Codex refuses its helper binaries in /tmp.
    home = Path.home() / f".{_SECRET}-codex"
    (home / tmp_path.name).mkdir(parents=True, exist_ok=True)
    yield binary, {**os.environ, "CODEX_HOME": str(home / tmp_path.name)}
    shutil.rmtree(home, ignore_errors=True)


def _refused(binary, profile, repo, env) -> str:
    """Why Codex refuses *profile* here: a platform refusal or a probe bug."""
    why = subprocess.run([binary, "sandbox", *profile, "--", *_shell(_cat(repo / "app.py"))],
                         cwd=repo, env=env, capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=60, check=False)
    version = subprocess.run([binary, "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", check=False).stdout.strip()
    return f"({version}, rc={why.returncode}): {(why.stderr or why.stdout).strip()[-400:]}"


def _inside(binary, profile, repo, env, script: str) -> bool:
    argv = [binary, "sandbox", *profile, "--", *_shell(script)]
    return subprocess.run(argv, cwd=repo, env=env, capture_output=True,
                          timeout=60, check=False).returncode == 0


def test_codex_profile_confines_when_the_probe_accepts_it(layout, codex):
    repo, _, secret = layout
    binary, env = codex
    profile = codex_sandbox.profile_args(Path.home().resolve(), [repo.resolve()])
    if not codex_sandbox.native_sandbox_works(binary, profile, repo, repo / "app.py", env):
        pytest.skip(f"Codex's home-limited profile is refused here {_refused(binary, profile, repo, env)}")
    assert _inside(binary, profile, repo, env, _cat(repo / "app.py")), "repo must stay readable"
    assert not _inside(binary, profile, repo, env, _cat(secret)), "home read leaked"
    assert not _inside(binary, profile, repo, env, _touch(repo / "pwned.txt")), "repo write leaked"
    assert not _inside(binary, profile, repo, env, _fetch()), "network leaked"


def test_codex_plain_read_only_confines_when_the_probe_accepts_it(layout, codex):
    repo, _, _ = layout
    binary, env = codex
    profile = codex_sandbox.plain_read_only_args()
    if not codex_sandbox.native_sandbox_works(binary, profile, repo, repo / "app.py", env):
        pytest.skip(f"Codex's read-only sandbox is refused here {_refused(binary, profile, repo, env)}")
    assert _inside(binary, profile, repo, env, _cat(repo / "app.py")), "repo must stay readable"
    assert not _inside(binary, profile, repo, env, _touch(repo / "pwned.txt")), "repo write leaked"
    assert not _inside(binary, profile, repo, env, _fetch()), "network leaked"


def test_this_interpreter_is_what_the_os_sandbox_reads_back():
    # runtime_readable_dirs must cover the interpreter the findings server runs on.
    dirs = [Path(d).resolve() for d in os_sandbox.runtime_readable_dirs()]
    assert any(Path(sys.executable).resolve().is_relative_to(d) for d in dirs)
