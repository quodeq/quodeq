"""Severity classes as a scoring path sees them: standards on disk plus the project's overrides."""
from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable, Mapping
from pathlib import Path

from quodeq.config.paths import default_paths
from quodeq.core.standards.overrides import OVERRIDES_RELPATH
from quodeq.core.standards.severity_classes import apply_severity_overrides
from quodeq.core.types.project_source import ProjectLocation
from quodeq.data.fs.project_files import read_repository_info
from quodeq.data.fs.standards_loader import read_severity_classes
from quodeq.data.fs.standards_prefs import load_project_overrides

_PATH_KEY = "path"
_LOCATION_KEY = "location"
_URL_MARK = "://"
_JSON_GLOB = "*.json"

# Parsed standards and overrides, keyed by where they came from and valid while
# the stat signature of their files is unchanged. A request pays stat calls, no reads.
_Signature = tuple
_cache_lock = threading.Lock()
_standards_cache: dict[tuple[str | None, str | None], tuple[_Signature, dict[str, str]]] = {}
_overrides_cache: dict[str, tuple[_Signature, dict[str, dict]]] = {}


def _stat_signature(path: Path) -> tuple[str, int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return path.name, st.st_size, st.st_mtime_ns


def _dir_signature(directory: Path | None) -> _Signature:
    """(name, size, mtime_ns) of each ``*.json`` in *directory*; stat only, no reads."""
    if directory is None or not directory.is_dir():
        return ()
    stats = (_stat_signature(path) for path in sorted(directory.glob(_JSON_GLOB)))
    return tuple(sig for sig in stats if sig is not None)


def _standard_dirs() -> tuple[Path | None, Path | None]:
    """(compiled_dir, evaluators_dir) exactly as a scan resolves them."""
    paths = default_paths()
    standards = paths.standards_dir
    compiled = (standards / "compiled") if standards and standards.exists() else None
    return compiled, paths.evaluators_dir


def _standards_classes(compiled_dir: Path | None, evaluators_dir: Path | None) -> dict[str, str]:
    key = (str(compiled_dir) if compiled_dir else None, str(evaluators_dir) if evaluators_dir else None)
    signature = (_dir_signature(compiled_dir), _dir_signature(evaluators_dir))
    with _cache_lock:
        cached = _standards_cache.get(key)
        if cached is not None and cached[0] == signature:
            return dict(cached[1])
    classes = read_severity_classes(compiled_dir, evaluators_dir)
    with _cache_lock:
        _standards_cache[key] = (signature, classes)
    return dict(classes)


def _project_overrides(repo_root: Path) -> dict[str, dict]:
    path = repo_root / OVERRIDES_RELPATH
    signature = _stat_signature(path)
    key = str(path)
    with _cache_lock:
        cached = _overrides_cache.get(key)
        if cached is not None and cached[0] == signature:
            return cached[1]
    overrides = load_project_overrides(repo_root)
    with _cache_lock:
        _overrides_cache[key] = (signature, overrides)
    return overrides


def load_severity_classes(
    repo_root: Path | None,
    *, standard_dirs_fn: Callable[[], tuple[Path | None, Path | None]] | None = None,
) -> dict[str, str]:
    """Compiled and custom classes, with *repo_root*'s ``.quodeq/standards-overrides.json`` applied.

    The standards and the overrides are re-read only when a file's size or
    modification time changed since the last call.
    """
    compiled_dir, evaluators_dir = (standard_dirs_fn or _standard_dirs)()
    classes = _standards_classes(compiled_dir, evaluators_dir)
    if repo_root is None:
        return classes
    return apply_severity_overrides(classes, _project_overrides(repo_root))


def _repo_root_of(run_dir: Path) -> Path | None:
    """The analysed working copy recorded beside the run, when it is a local directory.

    Same rule as the project attach gate: an online location or a URL-looking
    path has no working copy, otherwise the path must still be a directory.
    """
    info = read_repository_info(run_dir.parent)
    path = info.get(_PATH_KEY) if info else None
    if not isinstance(path, str) or not path:
        return None
    if str(info.get(_LOCATION_KEY, "")).lower() == ProjectLocation.ONLINE or _URL_MARK in path:
        return None
    root = Path(path)
    return root if root.is_dir() else None


def load_severity_classes_for_run(
    run_dir: Path,
    *, standard_dirs_fn: Callable[[], tuple[Path | None, Path | None]] | None = None,
) -> dict[str, str]:
    """Classes for the project a run belongs to (``<reports root>/<project>/<run>``)."""
    return load_severity_classes(_repo_root_of(run_dir), standard_dirs_fn=standard_dirs_fn)


def severity_classes_fingerprint(classes: Mapping[str, str]) -> str:
    """A stable digest of a class map, so grade tables can tell which classes they embody."""
    return hashlib.sha256(json.dumps(sorted(classes.items())).encode()).hexdigest()
