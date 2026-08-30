"""Wire serialization for source manifest models (JSON debugging dumps)."""
from __future__ import annotations

from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest


def target_to_dict(target: AnalysisTarget) -> dict:
    """Serialize for JSON debugging output."""
    return {
        "name": target.name,
        "language": target.language,
        "category": target.category,
        "frameworks": target.frameworks,
        "project_description": target.project_description,
        "total_files": target.total_files,
        "source_files_count": len(target.source_files),
        "language_stats": target.language_stats,
        "scope_path": target.scope_path,
    }


def manifest_to_dict(manifest: SourceManifest) -> dict:
    """Serialize for JSON debugging output."""
    return {
        "language": manifest.language,
        "category": manifest.category,
        "frameworks": manifest.frameworks,
        "project_description": manifest.project_description,
        "total_files": manifest.total_files,
        "source_files_count": len(manifest.source_files),
        "language_stats": manifest.language_stats,
        "targets": [target_to_dict(t) for t in manifest.targets],
    }
