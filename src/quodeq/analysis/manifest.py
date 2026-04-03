"""Source manifest — re-export hub for backward compatibility.

All public symbols that were historically imported from this module are
re-exported here so existing ``from quodeq.analysis.manifest import …``
statements continue to work unchanged.
"""
from __future__ import annotations

# Models
from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest  # noqa: F401

# Building
from quodeq.analysis.manifest_build import build_manifest, target_name  # noqa: F401

# Detection helpers (originally re-exported here)
from quodeq.analysis._detection import detect_language, list_source_files  # noqa: F401

# Rendering (originally re-exported here)
from quodeq.analysis.manifest_render import render_target_prompt_context  # noqa: F401
