"""Context-enrichment services that downweight false-positive findings.

The package exposes services (path-role classifier, project-shape detector,
precedent corpus) that wrap quodeq's existing dimension scanners. Each
service emits a confidence multiplier on top of the LLM's verdict; nothing
is suppressed.
"""
from quodeq.context.online_cache import (
    cache_disabled,
    cache_dir_for_url,
    cache_root,
    ensure_clone,
    is_inside_cache,
    repo_path_for_url,
    wipe_cache,
)
from quodeq.context.path_role import NON_PROD_ROLES, Role, path_role
from quodeq.context.precedent import fingerprint, load_precedent_fingerprints
from quodeq.context.project_shape import Deployment, ProjectShape, detect_shape

__all__ = [
    "Deployment",
    "NON_PROD_ROLES",
    "ProjectShape",
    "Role",
    "cache_disabled",
    "cache_dir_for_url",
    "cache_root",
    "detect_shape",
    "ensure_clone",
    "fingerprint",
    "is_inside_cache",
    "load_precedent_fingerprints",
    "path_role",
    "repo_path_for_url",
    "wipe_cache",
]
