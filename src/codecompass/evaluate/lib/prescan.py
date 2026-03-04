from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_MAX_FILE_BYTES = 1 * 1024 * 1024  # 1 MB

_IGNORE_DIRS = frozenset({
    "node_modules", ".gradle", "build", "dist", ".next",
    "__pycache__", ".mypy_cache", ".pytest_cache",
    ".git", ".svn", ".hg",
    ".idea", ".vscode", ".eclipse",
    "target", "out", "bin", "obj",
    ".venv", "venv", "env",
    ".terraform",
})


@lru_cache(maxsize=128)
def run_prescan_metrics(work_dir: str, discipline: str) -> str:
    root = Path(work_dir)
    file_count = 0
    line_count = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _IGNORE_DIRS for part in path.relative_to(root).parts):
            continue
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                file_count += 1
                continue
            raw = path.read_bytes()
            if b"\x00" in raw:  # binary guard
                file_count += 1
                continue
            line_count += raw.decode("utf-8", errors="ignore").count("\n")
            file_count += 1
        except OSError:
            continue
    return f"Discipline: {discipline}\nFiles: {file_count}\nLines: {line_count}\n"
