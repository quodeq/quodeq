"""Severity classes as a scoring path sees them: standards on disk plus the project's overrides."""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from quodeq.config.paths import default_paths
from quodeq.core.standards.severity_classes import apply_severity_overrides
from quodeq.data.fs.standards_loader import read_severity_classes
from quodeq.data.fs.standards_prefs import load_project_overrides

_REPO_INFO = "repository_info.json"
_PATH_KEY = "path"
_URL_PREFIXES = ("http://", "https://", "git@", "ssh://")


def _standard_dirs() -> tuple[Path | None, Path | None]:
    """(compiled_dir, evaluators_dir) exactly as a scan resolves them."""
    paths = default_paths()
    standards = paths.standards_dir
    compiled = (standards / "compiled") if standards and standards.exists() else None
    return compiled, paths.evaluators_dir


def load_severity_classes(
    repo_root: Path | None,
    *, standard_dirs_fn: Callable[[], tuple[Path | None, Path | None]] | None = None,
) -> dict[str, str]:
    """Compiled and custom classes, with *repo_root*'s ``.quodeq/standards-overrides.json`` applied."""
    compiled_dir, evaluators_dir = (standard_dirs_fn or _standard_dirs)()
    classes = read_severity_classes(compiled_dir, evaluators_dir)
    if repo_root is None:
        return classes
    return apply_severity_overrides(classes, load_project_overrides(repo_root))


def _repo_root_of(run_dir: Path) -> Path | None:
    """The analysed working copy recorded beside the run, when it is a local directory."""
    info_path = run_dir.parent / _REPO_INFO
    try:
        data = json.loads(info_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    path = data.get(_PATH_KEY) if isinstance(data, dict) else None
    if not isinstance(path, str) or path.startswith(_URL_PREFIXES):
        return None
    root = Path(path)
    return root if root.is_dir() else None


def load_severity_classes_for_run(run_dir: Path) -> dict[str, str]:
    """Classes for the project a run belongs to (``<reports root>/<project>/<run>``)."""
    return load_severity_classes(_repo_root_of(run_dir))
