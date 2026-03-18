"""Language detection helpers — extracted from manifest.py for size."""
from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from quodeq.shared.utils import read_json


def _walk_source_files(
    src: Path, extensions: set[str], skip_dirs: frozenset[str],
) -> Iterator[tuple[str, str]]:
    """Yield (relative_path, suffix) for source files, pruning skip dirs."""
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fname in filenames:
            suffix = os.path.splitext(fname)[1]
            if suffix in extensions:
                yield os.path.relpath(os.path.join(dirpath, fname), src), suffix


def list_source_files(src: Path, extensions: set[str], skip_dirs: frozenset[str] = frozenset()) -> list[str]:
    """List source files under *src* as paths relative to *src*."""
    files = [rel for rel, _ in _walk_source_files(src, extensions, skip_dirs)]
    files.sort()
    return files


def detect_language(src: Path, detection_file: Path) -> str:
    """Auto-detect the primary language for a repository using detection.json.

    Uses a two-pass approach:
    1. Check for config files at repo root (strong signal)
    2. Fall back to counting source files by extension (weak signal)
    """
    detection = read_json(detection_file)
    ext_map: dict[str, str] = detection.get("extensions", {})
    config_map: dict[str, str] = detection.get("config_files", {})
    skip_dirs = frozenset(detection.get("skip_dirs", []))

    # Pass 1: config files
    config_hits: Counter[str] = Counter()
    for config_file, lang in config_map.items():
        if (src / config_file).exists():
            config_hits[lang] += 1
    if config_hits:
        return config_hits.most_common(1)[0][0]

    # Pass 2: extension counts
    all_exts = set(ext_map.keys())
    lang_counts: Counter[str] = Counter()
    for _rel, suffix in _walk_source_files(src, all_exts, skip_dirs):
        lang = ext_map.get(suffix)
        if lang:
            lang_counts[lang] += 1
    if lang_counts:
        return lang_counts.most_common(1)[0][0]

    raise ValueError(f"No language detected in {src} using {detection_file}")
