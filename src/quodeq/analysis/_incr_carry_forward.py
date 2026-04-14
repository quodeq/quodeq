"""Carry forward — copy findings for unchanged files from previous runs."""
from __future__ import annotations

import json as _json
import logging
from pathlib import Path

_logger = logging.getLogger(__name__)


def carry_forward_findings(
    prev_jsonl: Path, output_jsonl: Path, unchanged_files: set[str],
    open_fn=None,
) -> int:
    """Copy findings for unchanged files from previous JSONL to output. Returns count.

    *open_fn* is an injectable file opener; defaults to the built-in ``open``.
    """
    if not prev_jsonl.exists():
        return 0
    _open = open_fn or open
    count = 0
    try:
        output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with _open(prev_jsonl) as inp, _open(output_jsonl, "a") as out:
            for line in inp:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                if entry.get("file") in unchanged_files:
                    out.write(_json.dumps(entry) + "\n")
                    count += 1
    except OSError as exc:
        _logger.warning(
            "Carry-forward failed for %s: %s. "
            "Check file permissions and that the output directory is writable.",
            prev_jsonl, exc,
        )
        return 0
    return count
