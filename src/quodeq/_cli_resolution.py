"""Evaluation input resolution — repo, language, manifest, and scope helpers.

Split from ``_cli_evaluation.py`` to keep each module under 300 lines.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile as _tempfile
from dataclasses import dataclass
from pathlib import Path

from quodeq.config.paths import default_paths
from quodeq.shared.utils import is_repo_url, project_name_from_repo, read_json
from quodeq.shared.validation import validate_path_segment
from quodeq.analysis.manifest import SourceManifest, build_manifest, detect_language
from quodeq.analysis.manifest_models import AnalysisTarget
from quodeq.analysis.runner import load_universal_dimensions

import logging

_logger = logging.getLogger(__name__)

_WORKTREE_TIMEOUT_S = 30


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


# ---------------------------------------------------------------------------
# Worktree management
# ---------------------------------------------------------------------------

def _create_worktree(repo_dir: Path, branch: str) -> Path | None:
    """Create a temporary git worktree for the given branch.

    Returns the worktree path, or None on failure.
    """
    worktree_dir = Path(_tempfile.mkdtemp(prefix=f"quodeq-wt-{branch.replace('/', '-')}-"))
    try:
        subprocess.run(
            ["git", "-C", str(repo_dir), "worktree", "add", str(worktree_dir), branch],
            capture_output=True, text=True, check=True, timeout=_WORKTREE_TIMEOUT_S,
        )
        return worktree_dir
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        print(f"Failed to create worktree for branch '{branch}': {exc}", file=sys.stderr)
        try:
            worktree_dir.rmdir()
        except OSError:
            pass
        return None


def _cleanup_worktree(repo_dir: Path, worktree_dir: Path) -> None:
    """Remove a temporary git worktree."""
    try:
        subprocess.run(
            ["git", "-C", str(repo_dir), "worktree", "remove", str(worktree_dir), "--force"],
            capture_output=True, text=True, timeout=_WORKTREE_TIMEOUT_S,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        _logger.debug("Failed to clean up worktree %s: %s", worktree_dir, exc)


# ---------------------------------------------------------------------------
# Repo / language / manifest resolution
# ---------------------------------------------------------------------------

def _resolve_repo(args: argparse.Namespace) -> Path | None:
    """Resolve the repo argument to a local path (cloning if needed)."""
    from quodeq.shared.repo_handler import cleanup_cloned_repo, prepare_repository

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
        worktree = _create_worktree(src, branch)
        if worktree is None:
            return None
        args._worktree_origin = src
        args._worktree_dir = worktree
        src = worktree

    return src


def _resolve_language(args: argparse.Namespace, src: Path, paths) -> str | None:
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


def _build_manifest(
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
    return manifest


# ---------------------------------------------------------------------------
# Scope and single-file resolution
# ---------------------------------------------------------------------------

def _resolve_scope(src: Path, args: argparse.Namespace) -> tuple[str | None, bool]:
    """Resolve --scope flag against the source directory.

    Returns ``(scope_path, ok)`` where *ok* is False when validation fails
    (error already printed to stderr).
    """
    scope = getattr(args, "scope", None)
    if not scope or not src.is_dir():
        return None, True
    scoped = (src / scope).resolve()
    if not scoped.exists():
        print(f"Scope path does not exist: {scoped}", file=sys.stderr)
        return None, False
    if not scoped.is_relative_to(src):
        print(f"Scope must be within the repository: {scope}", file=sys.stderr)
        return None, False
    kind = "file" if scoped.is_file() else "folder"
    print(f"Scoped evaluation: {scope} ({kind}, repo root: {src})", file=sys.stderr)
    return scope, True


def _resolve_single_file(src: Path) -> tuple[Path, str | None]:
    """Detect single-file mode and return (project_root, relative_path | None)."""
    if not src.is_file():
        return src, None
    file_path = src
    project_root = file_path.parent
    candidate = file_path.parent
    while candidate != candidate.parent:
        if (candidate / ".git").exists():
            project_root = candidate
            break
        candidate = candidate.parent
    single_file = str(file_path.relative_to(project_root))
    print(f"Single-file evaluation: {single_file} (project root: {project_root})", file=sys.stderr)
    return project_root, single_file


def _filter_manifest_by_scope(
    manifest: "SourceManifest | None", scope_path: str,
) -> "SourceManifest | None":
    """Narrow a manifest to only files under *scope_path*.

    Returns None (with error printed) when no files match.
    """
    if not manifest or not manifest.targets:
        return manifest

    prefix = scope_path.rstrip("/") + "/"
    scoped_targets: list[AnalysisTarget] = []
    total = 0
    all_stats: dict[str, int] = {}

    for t in manifest.targets:
        scoped_files = [f for f in t.source_files if f.startswith(prefix) or f == scope_path]
        if not scoped_files:
            continue
        stats: dict[str, int] = {}
        for f in scoped_files:
            ext = os.path.splitext(f)[1]
            if ext:
                stats[ext] = stats.get(ext, 0) + 1
        scoped_targets.append(AnalysisTarget(
            name=t.name, language=t.language,
            source_files=scoped_files, total_files=len(scoped_files),
            language_stats=stats, category=t.category,
        ))
        total += len(scoped_files)
        for k, v in stats.items():
            all_stats[k] = all_stats.get(k, 0) + v

    if scoped_targets:
        print(f"Scope filter: {total} files under '{scope_path}'", file=sys.stderr)
        return SourceManifest(targets=scoped_targets, total_files=total, language_stats=all_stats)

    print(f"No source files found under scope '{scope_path}'", file=sys.stderr)
    print("The scoped folder contains no recognized source code files.", file=sys.stderr)
    return None


def _override_manifest_single_file(
    language: str, single_file: str, args: argparse.Namespace,
) -> SourceManifest:
    """Create a single-file manifest and flag args for single-file mode."""
    ext = os.path.splitext(single_file)[1]
    target = AnalysisTarget(
        name=single_file, language=language,
        source_files=[single_file], total_files=1,
        language_stats={ext: 1} if ext else {},
    )
    args._single_file = True
    return SourceManifest(targets=[target], total_files=1, language_stats={ext: 1} if ext else {})


def _resolve_evaluation_inputs(args: argparse.Namespace) -> ResolvedInputs | None:
    """Resolve src, language, manifest, and dims_data from CLI args.

    Returns ``None`` (with error printed to stderr) if any step fails.
    """
    src = _resolve_repo(args)
    if src is None:
        return None

    scope_path, ok = _resolve_scope(src, args)
    if not ok:
        return None

    src, single_file = _resolve_single_file(src)

    paths = default_paths()
    if not paths.detection_file.exists() or not paths.dimensions_file.exists():
        print(
            "Configuration not found: detection.json and dimensions.json are required. "
            "These files are created automatically when you install Quodeq standards. "
            f"Expected location: {paths.detection_file.parent}",
            file=sys.stderr,
        )
        return None

    language = _resolve_language(args, src, paths)
    if language is None:
        return None

    try:
        dims_data = load_universal_dimensions(paths.dimensions_file)
    except ValueError as exc:
        print(f"Invalid dimensions config: {exc}", file=sys.stderr)
        return None

    manifest = _build_manifest(args, src, paths, scope_path=scope_path)

    if scope_path and manifest:
        manifest = _filter_manifest_by_scope(manifest, scope_path)
        if manifest is None:
            return None

    if single_file:
        manifest = _override_manifest_single_file(language, single_file, args)

    return ResolvedInputs(src=src, language=language, manifest=manifest, dims_data=dims_data)
