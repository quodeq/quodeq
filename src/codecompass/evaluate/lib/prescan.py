from __future__ import annotations

from pathlib import Path


def run_prescan_metrics(work_dir: str, discipline: str) -> str:
    root = Path(work_dir)
    file_count = 0
    line_count = 0
    for path in root.rglob("*"):
        if path.is_file():
            file_count += 1
            try:
                line_count += len(path.read_text(errors="ignore").splitlines())
            except OSError:
                continue
    return f"Discipline: {discipline}\nFiles: {file_count}\nLines: {line_count}\n"
