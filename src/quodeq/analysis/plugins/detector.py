"""Plugin detection — select the best language for a repository."""
from __future__ import annotations

import json
import logging
import os
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from quodeq.shared.utils import read_json

_logger = logging.getLogger(__name__)


_LEGACY_SKIP_DIRS = frozenset({
    "node_modules", "vendor", "venv", ".venv", "__pycache__",
    "dist", "build", "out", ".next", "target",
    ".git", ".svn", ".hg",
})


def _load_skip_dirs(detection: dict | None) -> frozenset[str]:
    """Return skip dirs from detection config or legacy default."""
    if detection and "skip_dirs" in detection:
        return frozenset(detection["skip_dirs"])
    return _LEGACY_SKIP_DIRS


def _walk_source_files(
    src: Path, extensions: set[str], skip_dirs: frozenset[str] | None = None,
) -> Iterator[tuple[str, str]]:
    """Yield (relative_path, suffix) for source files, pruning skip dirs."""
    skip = skip_dirs if skip_dirs is not None else _LEGACY_SKIP_DIRS
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fname in filenames:
            suffix = os.path.splitext(fname)[1]
            if suffix in extensions:
                yield os.path.relpath(os.path.join(dirpath, fname), src), suffix


def count_source_files(src: Path, extensions: set[str]) -> int:
    """Count files under *src* whose suffix is in *extensions*."""
    return sum(1 for _ in _walk_source_files(src, extensions))


def list_source_files(src: Path, extensions: set[str]) -> list[str]:
    """List source files under *src* as paths relative to *src*.

    Excludes vendored/generated directories.
    """
    files = [rel for rel, _ in _walk_source_files(src, extensions)]
    files.sort()
    return files


def _detect_by_config_files(plugins: list[dict], src: Path) -> str | None:
    """Pass 1: return the plugin with the most matching config-file hits, or None."""
    config_matches: list[tuple[int, str]] = []
    for data in plugins:
        config_files = data.get("detects", {}).get("config_files", [])
        hits = sum(1 for cf in config_files if (src / cf).exists())
        if hits > 0:
            config_matches.append((hits, data.get("id", "")))
    if not config_matches:
        return None
    config_matches.sort(key=lambda x: x[0], reverse=True)
    return config_matches[0][1]


def _detect_by_extension_count(plugins: list[dict], src: Path) -> str | None:
    """Pass 2: return the plugin whose file extensions are most prevalent, or None.

    Performs a single rglob traversal to collect suffix counts, then scores each
    plugin in O(1) per extension -- O(n) total regardless of plugin count.
    """
    all_exts: set[str] = set()
    for data in plugins:
        all_exts.update(data.get("detects", {}).get("extensions", []))
    suffix_counts: Counter[str] = Counter()
    for _rel, suffix in _walk_source_files(src, all_exts):
        suffix_counts[suffix] += 1
    if not suffix_counts:
        return None
    best_id: str | None = None
    best_count = 0
    for data in plugins:
        exts = set(data.get("detects", {}).get("extensions", []))
        if not exts:
            continue
        count = sum(suffix_counts.get(ext, 0) for ext in exts)
        if count > best_count:
            best_count = count
            best_id = data.get("id", "")
    return best_id


def detect_plugin(src: Path, evaluators_dir: Path) -> str:
    """Auto-detect the best plugin for a repository.

    Uses a two-pass approach:
    1. Check for config files at repo root (strong signal -- e.g. pyproject.toml -> python)
    2. Fall back to counting source files by extension (weak signal)
    """
    plugins: list[dict] = []
    for child in sorted(evaluators_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        pf = child / "plugin.json"
        if not pf.exists():
            continue
        try:
            data = json.loads(pf.read_text())
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            _logger.warning("Skipping malformed plugin.json in %s: %s", pf.parent.name, exc)
            continue
        plugins.append(data)

    plugin_id = _detect_by_config_files(plugins, src) or _detect_by_extension_count(plugins, src)
    if plugin_id is None:
        raise ValueError(f"No plugin in {evaluators_dir} matched any file in {src}")
    return plugin_id


def detect_language(src: Path, detection_file: Path) -> str:
    """Auto-detect the primary language for a repository using detection.json.

    Uses a two-pass approach:
    1. Check for config files at repo root (strong signal)
    2. Fall back to counting source files by extension (weak signal)
    """
    detection = read_json(detection_file)
    ext_map: dict[str, str] = detection.get("extensions", {})
    config_map: dict[str, str] = detection.get("config_files", {})
    skip_dirs = _load_skip_dirs(detection)

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
