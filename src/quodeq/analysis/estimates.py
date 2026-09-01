"""Read-only pre-run estimates for a project, mirroring run-start resolution.

Backs ``GET /api/projects/<project>/estimates``. Lives in the analysis layer
because everything it composes (language detection, manifest build, dimension
resolution, ``compute_dim_estimates``) is analysis code; the API route only
imports this one entry point.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.analysis._analysis_context import load_analysis_context
from quodeq.analysis._dim_estimates import compute_dim_estimates
from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.analysis.dispatch_policy import default_dispatch_policy
from quodeq.analysis.manifest import build_manifest, detect_language
from quodeq.analysis.manifest_scope import _filter_manifest_by_scope
from quodeq.analysis.runner import load_universal_dimensions
from quodeq.config.paths import default_paths
from quodeq.shared.utils import read_json

EMPTY_ESTIMATES_PAYLOAD = {
    "dimensions": {}, "projectFiles": 0, "cachedFiles": 0, "changedFiles": 0,
}


def _resolve_repo_source(project_dir: Path) -> tuple[Path, str | None] | None:
    """Resolve the project's source path and scope from repository_info.json.

    Returns None when the info file is missing/unreadable or the recorded
    path no longer exists, signalling the caller to degrade to zeros.
    """
    info_path = project_dir / "repository_info.json"
    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    src = Path(info.get("path") or "")
    if not info.get("path") or not src.is_dir():
        return None
    return src, info.get("scopePath") or None


def _build_estimate_config(
    src: Path,
    scope_path: str | None,
    requested: list[str] | None,
    clean_scan: bool,
) -> RunConfig | None:
    """Build the RunConfig used to compute estimates, mirroring run start.

    Returns None when detection/dimensions data isn't available yet or
    language detection fails, signalling the caller to degrade to zeros.
    """
    paths = default_paths()
    if not paths.detection_file.exists() or not paths.dimensions_file.exists():
        return None
    try:
        language = detect_language(src, paths.detection_file)
        dims_data = load_universal_dimensions(paths.dimensions_file)
    except ValueError:
        return None

    detection = read_json(paths.detection_file)
    disciplines_conf = paths.disciplines_conf if paths.disciplines_conf.exists() else None
    manifest = build_manifest(src, detection, disciplines_conf, scope_path=scope_path)
    if scope_path and manifest:
        # None (no files under scope) flows through: every dim then
        # estimates as {"count": 0, "reason": "empty"}.
        manifest = _filter_manifest_by_scope(manifest, scope_path)

    standards_dir = paths.standards_dir
    return RunConfig(
        src=src,
        language=language,
        standards_dir=standards_dir if standards_dir.exists() else None,
        manifest=manifest,
        dimensions_data=dims_data,
        evaluators_dir=paths.evaluators_dir,
        prompts_dir=paths.prompts_dir,
        options=AnalysisOptions(dimensions=requested, incremental=not clean_scan),
        dispatch=default_dispatch_policy(),
    )


def _aggregate_project_totals(estimates: dict) -> dict:
    """Aggregate per-dim estimate counts into the project-wide totals payload.

    Only per-dim counts exist here (no per-file identity), so the
    project-wide numbers are per-dim-consistent aggregates: every dim
    enumerates the same dispatchable file set, so ``total`` agrees across
    dims and ``count`` differs only by per-dim cache state.
    projectFiles/changedFiles are the per-dim maxima and cachedFiles the
    complement, matching how scan_progress reports per-dim totals rather
    than a deduped cross-dim file set.
    """
    project_files = max((e["total"] for e in estimates.values()), default=0)
    changed_files = max((e["count"] for e in estimates.values()), default=0)
    cached_files = max(0, project_files - changed_files)
    return {
        "dimensions": estimates,
        "projectFiles": project_files,
        "cachedFiles": cached_files,
        "changedFiles": changed_files,
    }


def project_estimates_payload(
    project_dir: Path, requested: list[str] | None, clean_scan: bool,
) -> dict:
    """Compute read-only pre-run estimates for a project.

    Mirrors run-start input resolution (language detection, manifest build,
    dimension resolution via ``load_analysis_context``) without creating a
    run or writing anything to disk. Any resolution failure degrades to the
    zeros payload instead of an error: a project that was never scanned
    simply has nothing to estimate.
    """
    resolved = _resolve_repo_source(project_dir)
    if resolved is None:
        return dict(EMPTY_ESTIMATES_PAYLOAD)
    src, scope_path = resolved

    config = _build_estimate_config(src, scope_path, requested, clean_scan)
    if config is None:
        return dict(EMPTY_ESTIMATES_PAYLOAD)

    try:
        # load_analysis_context filters unknown requested dimensions the
        # same way run start does; ValueError means none were valid.
        dimensions, _ctx = load_analysis_context(config)
        estimates = compute_dim_estimates(config, dimensions)
    except (OSError, ValueError, KeyError, RuntimeError):
        return dict(EMPTY_ESTIMATES_PAYLOAD)

    return _aggregate_project_totals(estimates)
