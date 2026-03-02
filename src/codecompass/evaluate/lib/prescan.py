from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_MAX_FILE_BYTES = 1 * 1024 * 1024  # 1 MB


@lru_cache(maxsize=128)
def run_prescan_metrics(work_dir: str, discipline: str) -> str:
    root = Path(work_dir)
    file_count = 0
    line_count = 0
    for path in root.rglob("*"):
        if not path.is_file():
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
