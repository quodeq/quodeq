"""Dependency analysis — find files that import changed modules."""
from __future__ import annotations

import re
from pathlib import Path

from quodeq.analysis.subagents.priority import load_priority_config, _LANG_ALIASES


def _file_imports_changed(content: str, compiled: list, changed_stems: dict[str, str]) -> bool:
    """Return True if *content* imports any module whose stem is in *changed_stems*."""
    for line in content.splitlines():
        for pattern in compiled:
            m = pattern.search(line)
            if not m:
                continue
            module_name = m.group(1).rsplit(".", 1)[-1].rsplit("/", 1)[-1]
            if module_name in changed_stems:
                return True
            break
    return False


def _safe_read(path: Path) -> str | None:
    """Read a file's text, returning None if missing or unreadable."""
    if not path.exists():
        return None
    try:
        return path.read_text(errors="ignore")
    except OSError:
        return None


def find_dependents(changed: set[str], files: list[str], src: Path, language: str) -> set[str]:
    """Find files that directly import any changed file (1 level deep)."""
    config = load_priority_config()
    lang_key = _LANG_ALIASES.get(language.lower(), language.lower())
    patterns = config.get("import_patterns", {}).get(lang_key)
    if not patterns:
        return set()

    changed_stems = {Path(f).stem: f for f in changed}
    compiled = [re.compile(p) for p in patterns]
    dependents: set[str] = set()

    for f in files:
        if f in changed:
            continue
        full_path = src / f
        content = _safe_read(full_path)
        if content is not None and _file_imports_changed(content, compiled, changed_stems):
            dependents.add(f)
    return dependents
