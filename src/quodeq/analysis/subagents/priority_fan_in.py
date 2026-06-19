"""Fan-in analysis: counts how many files import each file."""
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
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None

    _read = read_file or _default_read

    # Build filename lookup: stem -> list of relative paths (multiple files may share a stem)
    stem_to_files: dict[str, list[str]] = {}
    for f in files:
        stem = Path(f).stem
        stem_to_files.setdefault(stem, []).append(f)

    compiled = [re.compile(p) for p in patterns]
    counts: dict[str, int] = {}

    for f in files:
        content = _read(src / f)
        if content is None:
            continue
        for line in content.splitlines():
            for target in _match_import_targets(line, compiled, stem_to_files, f):
                counts[target] = counts.get(target, 0) + 1

    return counts


def _match_import_targets(
    line: str, compiled: list[re.Pattern], stem_to_files: dict[str, list[str]], current_file: str,
) -> list[str]:
    """Match a single line against import patterns and return all matching target files.

    When multiple files share the same stem, the import path is used to narrow
    candidates: a candidate whose directory components appear in the import string
    is preferred.  All non-self candidates are returned so fan-in is credited to
    every file that could be the import target.
    """
    for pattern in compiled:
        m = pattern.search(line)
        if m:
            imported = m.group(1)
            module_name = imported.rsplit(".", 1)[-1].rsplit("/", 1)[-1]
            candidates = stem_to_files.get(module_name, [])
            # Filter out the importing file itself
            candidates = [c for c in candidates if c != current_file]
            if not candidates:
                return []
            # If only one candidate, return it directly
            if len(candidates) == 1:
                return candidates
            # Multiple candidates share the stem, so use the import path to disambiguate.
            # Build a normalised version of the import string for prefix matching.
            import_parts = imported.replace(".", "/").lower()
            preferred = [
                c for c in candidates
                if Path(c).parent.as_posix().lower() in import_parts
                or import_parts in Path(c).parent.as_posix().lower()
            ]
            return preferred if preferred else candidates
    return []
