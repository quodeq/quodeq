"""Wire serialization for source manifest models (JSON debugging dumps)."""
from __future__ import annotations

from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest
from quodeq.analysis.manifest_render import describe_target


def target_to_dict(target: AnalysisTarget) -> dict:
    """Serialize for JSON debugging output."""
    return {
        "name": target.name,
        "language": target.language,
        "category": target.category,
        "frameworks": target.frameworks,
        "project_description": describe_target(target),
        "total_files": target.total_files,
        "source_files_count": len(target.source_files),
        "language_stats": target.language_stats,
        "scope_path": target.scope_path,
    }


def manifest_to_dict(manifest: SourceManifest) -> dict:
    """Serialize for JSON debugging output."""
    # Mirrors SourceManifest._primary's delegation: describe the primary
    # target, "Unknown" when the manifest has none. The serialized
    # "project_description" KEY is part of the manifest.json shape.
    primary = manifest._primary
    return {
        "language": manifest.language,
        "category": manifest.category,
        "frameworks": manifest.frameworks,
        "project_description": describe_target(primary) if primary else "Unknown",
        "total_files": manifest.total_files,
        "source_files_count": len(manifest.source_files),
        "language_stats": manifest.language_stats,
        "targets": [target_to_dict(t) for t in manifest.targets],
    }
