"""Fan-in analysis — counts how many files import each file."""
from __future__ import annotations

import re
from pathlib import Path

from quodeq.analysis.subagents.priority_config import _LANG_ALIASES, load_priority_config


def compute_fan_in(
    files: list[str], src: Path, language: str,
    read_file=None,
) -> dict[str, int]:
    """Layer 3: count how many files import each file.

    *read_file* is an injectable ``(Path) -> str | None`` reader; defaults
    to reading from the filesystem.
    """
    config = load_priority_config()
    lang_key = _LANG_ALIASES.get(language.lower(), language.lower())
    patterns = config.get("import_patterns", {}).get(lang_key)
    if not patterns:
        return {}

    def _default_read(path: Path) -> str | None:
        if not path.exists():
            return None
        try:
            return path.read_text(errors="ignore")
        except OSError:
            return None

    _read = read_file or _default_read

    # Build filename lookup: stem -> relative path
    stem_to_file: dict[str, str] = {}
    for f in files:
        stem = Path(f).stem
        stem_to_file.setdefault(stem, f)

    compiled = [re.compile(p) for p in patterns]
    counts: dict[str, int] = {}

    for f in files:
        content = _read(src / f)
        if content is None:
            continue
        for line in content.splitlines():
            target = _match_import_target(line, compiled, stem_to_file, f)
            if target is not None:
                counts[target] = counts.get(target, 0) + 1

    return counts


def _match_import_target(
    line: str, compiled: list[re.Pattern], stem_to_file: dict[str, str], current_file: str,
) -> str | None:
    """Match a single line against import patterns and return the target file, or None."""
    for pattern in compiled:
        m = pattern.search(line)
        if m:
            imported = m.group(1)
            module_name = imported.rsplit(".", 1)[-1].rsplit("/", 1)[-1]
            target = stem_to_file.get(module_name)
            if target is not None and target != current_file:
                return target
            return None
    return None
