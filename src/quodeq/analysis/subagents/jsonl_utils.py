"""JSONL merge and deduplication utilities for subagent pool output."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from quodeq.shared.logging import log_info
from quodeq.shared.utils import open_text

_logger = logging.getLogger(__name__)


def dedup_jsonl_lines(lines: Iterable[str]) -> list[str]:
    """Deduplicate JSONL lines by ``(p, file, line, t)`` key.

    Returns a list of stripped, unique JSON lines.
    """
    return list(_iter_dedup_jsonl_lines(lines))


def _iter_dedup_jsonl_lines(lines: Iterable[str]) -> Iterable[str]:
    """Yield unique JSONL lines, deduplicating by ``(p, file, line, t)`` key.

    Uses a set for seen keys and yields each unique line immediately,
    avoiding accumulation of all lines in memory.
    """
    seen: set[tuple] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            _logger.debug("Skipping malformed JSONL line: %.100s", stripped)
            continue
        key = (obj.get("p"), obj.get("file"), obj.get("line"), obj.get("t"))
        if key in seen:
            continue
        seen.add(key)
        yield stripped


def deduplicate_jsonl(jsonl_path: Path) -> int:
    """Deduplicate a JSONL file in-place by (p, file, line, t).

    Returns the number of unique findings kept.
    """
    if not jsonl_path.exists():
        return 0
    # Read first, then overwrite — must fully consume before writing to same file
    with open_text(jsonl_path) as f:
        unique_lines = dedup_jsonl_lines(f)
    with open_text(jsonl_path, "w") as f:
        for line in unique_lines:
            f.write(line + "\n")
    log_info(f"Deduplicated {jsonl_path.name}: {len(unique_lines)} unique findings")
    return len(unique_lines)


def merge_jsonl(result_jsonl_files: Iterable[Path], output: Path) -> Path:
    """Merge JSONL files, deduplicating by (p, file, line, t).

    Writes deduplicated lines directly to the output file as they are found
    unique, avoiding accumulation of all lines in memory.

    Returns the output path.
    """
    def _iter_all_lines() -> Iterable[str]:
        for jsonl_file in result_jsonl_files:
            if not jsonl_file.exists():
                continue
            with open_text(jsonl_file) as f:
                yield from f

    count = 0
    with open_text(output, "w") as out:
        for line in _iter_dedup_jsonl_lines(_iter_all_lines()):
            out.write(line + "\n")
            count += 1
    log_info(f"Merged {count} unique findings into {output.name}")
    return output
