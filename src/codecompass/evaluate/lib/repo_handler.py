from __future__ import annotations

import shutil
from pathlib import Path
import subprocess


def is_repo_url(repo_input: str) -> bool:
    return repo_input.startswith(("http://", "https://", "git@"))


def _strip_gitignored(src_repo: Path, dest: Path) -> None:
    """Remove files/dirs from dest that are gitignored in src_repo."""
    result = subprocess.run(
        ["git", "ls-files", "--others", "--ignored", "--exclude-standard", "--directory"],
        cwd=str(src_repo),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return
    for rel in result.stdout.splitlines():
        rel = rel.strip().rstrip("/")
        if not rel:
            continue
        target = dest / rel
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.is_file():
            target.unlink(missing_ok=True)


def prepare_repository(repo_input: str) -> str:
    repo_root = Path(__file__).resolve().parents[3]
    tmp_base = repo_root / "tmp"
    tmp_base.mkdir(parents=True, exist_ok=True)

    if is_repo_url(repo_input):
        repo_name = repo_input.split("/")[-1].replace(".git", "")
        dest = tmp_base / repo_name
        subprocess.run(["git", "clone", repo_input, str(dest)], check=True)
        return str(dest.resolve())

    local_path = Path(repo_input).resolve()
    if not local_path.exists():
        raise FileNotFoundError(f"Local path {local_path} does not exist")

    dest = tmp_base / local_path.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(str(local_path), str(dest), ignore=shutil.ignore_patterns(".git"))
    _strip_gitignored(local_path, dest)
    return str(dest.resolve())
