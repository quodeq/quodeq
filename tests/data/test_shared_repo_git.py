"""The shared-repo git/path layer imports without the rest of shared_repo."""
from __future__ import annotations

import subprocess
import sys


def _modules_after_import(module: str) -> set[str]:
    code = f"import sys, {module}; print('\\n'.join(sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    return set(out.stdout.split())


def test_meta_imports_without_shared_repo():
    loaded = _modules_after_import("quodeq.data.fs.shared_repo_meta")
    assert "quodeq.data.fs.shared_repo_git" in loaded
    assert "quodeq.data.fs.shared_repo" not in loaded


def test_shared_repo_reexports_are_the_git_layer_objects():
    from quodeq.data.fs import shared_repo, shared_repo_git

    assert shared_repo.run_git is shared_repo_git.run_git
    assert shared_repo.shared_repo_path is shared_repo_git.shared_repo_path
