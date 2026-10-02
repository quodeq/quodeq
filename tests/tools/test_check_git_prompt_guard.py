"""Gate: git subprocesses close stdin and pass an explicit env (the prompt floor)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import check_git_prompt_guard

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def _write(tmp_path: Path, relpath: str, source: str) -> Path:
    f = tmp_path / relpath
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(source, encoding="utf-8")
    return f


def test_gate_passes_on_current_tree():
    proc = subprocess.run(
        [sys.executable, str(TOOLS / "check_git_prompt_guard.py")],
        capture_output=True, text=True, check=False, timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_flags_a_git_run_without_stdin(tmp_path):
    _write(tmp_path, "src/quodeq/x.py", "import subprocess\nsubprocess.run(['git', 'fetch'], env={}, timeout=5)\n")
    hits = check_git_prompt_guard.scan_tree(tmp_path / "src")
    assert [(h.path.name, h.line) for h in hits] == [("x.py", 2)]


def test_flags_a_git_bin_run_without_env(tmp_path):
    src = "import subprocess\nfrom quodeq.shared.constants import GIT_BIN\nsubprocess.run([GIT_BIN, 'x'], stdin=subprocess.DEVNULL, timeout=5)\n"
    _write(tmp_path, "src/quodeq/x.py", src)
    hits = check_git_prompt_guard.scan_tree(tmp_path / "src")
    assert [h.line for h in hits] == [3]


def test_accepts_a_guarded_call(tmp_path):
    src = "import subprocess\nsubprocess.run(['git', 'x'], env=git_env_floor(), stdin=subprocess.DEVNULL, timeout=5)\n"
    _write(tmp_path, "src/quodeq/x.py", src)
    assert check_git_prompt_guard.scan_tree(tmp_path / "src") == []


def test_ignores_non_git_subprocess(tmp_path):
    _write(tmp_path, "src/quodeq/x.py", "import subprocess\nsubprocess.run(['gh', 'auth', 'token'], timeout=5)\n")
    assert check_git_prompt_guard.scan_tree(tmp_path / "src") == []


def _hit_lines(tmp_path: Path, source: str) -> list[int]:
    _write(tmp_path, "src/quodeq/x.py", source)
    return [h.line for h in check_git_prompt_guard.scan_tree(tmp_path / "src")]


def test_flags_a_from_import_bare_run(tmp_path):
    assert _hit_lines(tmp_path, "from subprocess import run\nrun(['git', 'x'], timeout=5)\n") == [2]


def test_flags_an_aliased_subprocess_module(tmp_path):
    assert _hit_lines(tmp_path, "import subprocess as sp\nsp.run(['git', 'x'], timeout=5)\n") == [2]


def test_ignores_run_on_a_non_subprocess_receiver(tmp_path):
    assert _hit_lines(tmp_path, "import subprocess\nfoo.run(['git', 'x'], timeout=5)\n") == []


def test_flags_keyword_argv_without_stdin(tmp_path):
    src = "import subprocess\nsubprocess.run(args=['git', 'x'], env={}, timeout=5)\n"
    assert _hit_lines(tmp_path, src) == [2]
