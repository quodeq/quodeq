"""Evaluation input resolution — repo, language, manifest, and scope helpers.

Split from ``cli_evaluation.py`` to keep each module under 300 lines.
Worktree management lives in ``_cli_worktree.py``; re-exported here (and, in
turn, from ``cli_evaluation.py``) so ``quodeq._cli_resolution.create_worktree``
and ``quodeq.cli_evaluation.cleanup_worktree`` stay valid patch targets.
``import subprocess`` stays in this module even though the worktree
functions moved out — ``resolve_repo`` below still needs the exception
types, and tests patch ``quodeq._cli_resolution.subprocess.run``, which
requires this module to expose a ``subprocess`` attribute. ``FETCH_TIMEOUT_S``
also stays here (rather than moving with ``_fetch_branch``) because a test
reloads this module with ``QUODEQ_GIT_CLONE_TIMEOUT_S`` set and reads the
import-time constant back off it; ``_cli_worktree._fetch_branch`` reads it
via a deferred facade lookup.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from quodeq.config.clone_env import git_clone_timeout_s
from quodeq.config.paths import default_paths
from quodeq.shared.utils import is_repo_url, read_json
from quodeq.shared.validation import validate_path_segment
from quodeq.analysis.manifest import SourceManifest, build_manifest, detect_language
# Re-exported: moved to the analysis layer (pure manifest logic); CLI modules
# keep their historical `from quodeq._cli_resolution import ...` path.
from quodeq.analysis.manifest_scope import filter_manifest_by_scope
from quodeq.analysis.runner import load_universal_dimensions
from quodeq.shared.log_sink import SHARED_LOG
# Re-exported: moved to _cli_worktree.py to keep this module under 300 lines.
# cleanup_worktree is unused directly in this module but must stay imported
# — it is a patch target (quodeq._cli_resolution.cleanup_worktree) and the
# public re-export chain through quodeq.cli_evaluation depends on it.
from quodeq._cli_worktree import cleanup_worktree, create_worktree
# Re-exported: moved to _cli_scope.py to keep this module under 300 lines.
from quodeq._cli_scope import (
    override_manifest_single_file, resolve_scope, resolve_single_file,
)

# Branch fetches (_cli_worktree._fetch_branch) go over the network; give them
# the clone budget, not the local worktree one. Stays an import-time constant
# here — see the module docstring for why.
FETCH_TIMEOUT_S = git_clone_timeout_s()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ResolvedInputs:
    """Grouped evaluation inputs that always travel together."""
    src: Path
    language: str
    manifest: object  # SourceManifest | None
    dims_data: dict
    worktree_origin: Path | None = None
    worktree_dir: Path | None = None
    single_file: bool = False


# ---------------------------------------------------------------------------
# Repo / language / manifest resolution
# ---------------------------------------------------------------------------

def resolve_repo(args: argparse.Namespace) -> tuple[Path, Path | None, Path | None] | None:
    """Resolve the repo argument to a local path (cloning if needed).

    Returns ``(src, worktree_origin, worktree_dir)`` where the worktree
    fields are non-None only when a temporary branch worktree was created,
    or ``None`` (with error printed to stderr) on failure.
    """
    from quodeq.data.fs.repo_handler import prepare_repository

    repo_path = args.repo
    try:
        is_remote = is_repo_url(repo_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return None
    if is_remote:
        try:
            repo_path = prepare_repository(repo_path)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as exc:
            print(f"Failed to clone repository: {exc}", file=sys.stderr)
            return None
    src = Path(repo_path).resolve()
    if not src.exists():
        print(f"Repository path does not exist: {src}. Verify the path is correct and accessible.", file=sys.stderr)
        return None

    branch = getattr(args, "branch", None)
    if branch and not is_remote and src.is_dir():
        worktree = create_worktree(src, branch)
        if worktree is None:
            return None
        return worktree, src, worktree

    return src, None, None


def resolve_language(args: argparse.Namespace, src: Path, paths) -> str | None:
    """Detect or validate the language for a repo using universal detection."""
    if args.language:
        validate_path_segment(args.language)
        return args.language
    if not paths.detection_file.exists():
        return None
    try:
        return detect_language(src, paths.detection_file)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return None


def build_cli_manifest(
    args: argparse.Namespace, src: Path, paths,
    scope_path: str | None = None,
) -> "SourceManifest | None":
    """Build a source manifest for the repository."""
    if args.no_prescan:
        return None

    detection_file = paths.detection_file
    if not detection_file.exists():
        return None

    detection = read_json(detection_file)
    disciplines_conf = paths.disciplines_conf if paths.disciplines_conf.exists() else None
    manifest = build_manifest(src, detection, disciplines_conf, scope_path=scope_path)
    if manifest.targets:
        langs = ", ".join(
            f"{t.language} ({t.total_files})"
            for t in manifest.targets
        )
        print(f"Detected: {langs}", file=sys.stderr)
    print(f"Source files: {manifest.total_files}", file=sys.stderr)
    skipped = manifest.skipped_untracked
    if skipped:
        print(
            f"Skipped {skipped} untracked file{'' if skipped == 1 else 's'} "
            "(only what git tracks is scored)",
            file=sys.stderr,
        )
    return manifest


def require_standards_config(paths) -> bool:
    """Return True if detection.json/dimensions.json exist; else print and return False."""
    if paths.detection_file.exists() and paths.dimensions_file.exists():
        return True
    print(
        "Configuration not found: detection.json and dimensions.json are required. "
        "These files are created automatically when you install Quodeq standards. "
        f"Expected location: {paths.detection_file.parent}",
        file=sys.stderr,
    )
    return False


class _SourceScope(NamedTuple):
    """Where the evaluation reads from, once repo, --scope and single-file are settled."""
    src: Path
    worktree_origin: Path | None
    worktree_dir: Path | None
    scope_path: str | None
    single_file: str | None


def _resolve_source_scope(args: argparse.Namespace) -> _SourceScope | None:
    """Resolve the repo, the --scope subtree and single-file mode into one record.

    Returns ``None`` (with error printed to stderr) if any step fails.
    """
    resolved = resolve_repo(args)
    if resolved is None:
        return None
    src, worktree_origin, worktree_dir = resolved

    scope_path, ok = resolve_scope(src, args)
    if not ok:
        return None

    src, single_file = resolve_single_file(src)
    return _SourceScope(src, worktree_origin, worktree_dir, scope_path, single_file)


def _load_dimensions(paths) -> dict | None:
    """Load the universal dimensions config; None (with error printed) if invalid."""
    try:
        return load_universal_dimensions(paths.dimensions_file)
    except ValueError as exc:
        print(f"Invalid dimensions config: {exc}", file=sys.stderr)
        return None


def _resolve_manifest(
    args: argparse.Namespace, paths, scope: _SourceScope, language: str,
) -> "SourceManifest | None | object":
    """Build the manifest, narrow it to --scope, or replace it with the single file.

    Returns ``_SCOPE_EMPTY`` when --scope matched no file, which is a failure
    rather than the "no prescan" None that ``build_cli_manifest`` can return.
    """
    manifest = build_cli_manifest(args, scope.src, paths, scope_path=scope.scope_path)
    if scope.scope_path and manifest:
        manifest = filter_manifest_by_scope(manifest, scope.scope_path, log=SHARED_LOG)
        if manifest is None:
            return _SCOPE_EMPTY
    if scope.single_file:
        return override_manifest_single_file(language, scope.single_file)
    return manifest


_SCOPE_EMPTY = object()
"""Marker: --scope excluded every file, so the run has nothing to evaluate."""


def resolve_evaluation_inputs(args: argparse.Namespace) -> ResolvedInputs | None:
    """Resolve src, language, manifest, and dims_data from CLI args.

    Returns ``None`` (with error printed to stderr) if any step fails.
    """
    scope = _resolve_source_scope(args)
    if scope is None:
        return None

    paths = default_paths()
    if not require_standards_config(paths):
        return None

    language = resolve_language(args, scope.src, paths)
    if language is None:
        return None

    dims_data = _load_dimensions(paths)
    if dims_data is None:
        return None

    manifest = _resolve_manifest(args, paths, scope, language)
    if manifest is _SCOPE_EMPTY:
        return None

    return ResolvedInputs(
        src=scope.src, language=language, manifest=manifest, dims_data=dims_data,
        worktree_origin=scope.worktree_origin, worktree_dir=scope.worktree_dir,
        single_file=bool(scope.single_file),
    )


__all__ = [
    # Defined here.
    "ResolvedInputs", "filter_manifest_by_scope",
    "build_cli_manifest", "require_standards_config", "resolve_evaluation_inputs",
    "resolve_language", "resolve_repo",
    # Re-exported from _cli_scope / _cli_worktree so the historical
    # ``quodeq._cli_resolution.<name>`` import and patch paths keep working.
    "cleanup_worktree", "create_worktree",
    "override_manifest_single_file", "resolve_scope", "resolve_single_file",
]
