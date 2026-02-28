from __future__ import annotations

from pathlib import Path
import subprocess


def is_repo_url(repo_input: str) -> bool:
    return repo_input.startswith(("http://", "https://", "git@"))


def prepare_repository(repo_input: str) -> str:
    repo_root = Path(__file__).resolve().parents[3]
    if is_repo_url(repo_input):
        repo_name = repo_input.split("/")[-1].replace(".git", "")
        dest = repo_root / "tmp" / repo_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", repo_input, str(dest)], check=True)
        return str(dest.resolve())

    local_path = Path(repo_input).resolve()
    if not local_path.exists():
        raise FileNotFoundError(f"Local path {local_path} does not exist")
    return str(local_path)
