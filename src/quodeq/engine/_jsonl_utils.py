"""JSONL merge and deduplication utilities for subagent pool output."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from quodeq.shared.logging import log_info


def dedup_jsonl_lines(lines: Iterable[str]) -> list[str]:
    """Deduplicate JSONL lines by ``(p, file, line, t)`` key.

    Returns a list of stripped, unique JSON lines.
    """
    seen: set[tuple] = set()
    unique: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        key = (obj.get("p"), obj.get("file"), obj.get("line"), obj.get("t"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(stripped)
    return unique


def deduplicate_jsonl(jsonl_path: Path) -> int:
    """Deduplicate a JSONL file in-place by (p, file, line, t).

    Returns the number of unique findings kept.
    """
    if not jsonl_path.exists():
        return 0
    with open(jsonl_path) as f:
        unique_lines = dedup_jsonl_lines(f)
    with open(jsonl_path, "w") as f:
        for line in unique_lines:
            f.write(line + "\n")
    log_info(f"Deduplicated {jsonl_path.name}: {len(unique_lines)} unique findings")
    return len(unique_lines)


def merge_jsonl(result_jsonl_files: Iterable[Path], output: Path) -> Path:
    """Merge JSONL files, deduplicating by (p, file, line, t).

    Returns the output path.
    """
    def _iter_all_lines() -> Iterable[str]:
        for jsonl_file in result_jsonl_files:
            if not jsonl_file.exists():
                continue
            with open(jsonl_file) as f:
                yield from f

    unique_lines = dedup_jsonl_lines(_iter_all_lines())
    with open(output, "w") as out:
        for line in unique_lines:
            out.write(line + "\n")
    log_info(f"Merged {len(unique_lines)} unique findings into {output.name}")
    return output
