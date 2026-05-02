"""Context-enrichment services that downweight false-positive findings.

The package exposes services (path-role classifier, project-shape detector,
precedent corpus) that wrap quodeq's existing dimension scanners. Each
service emits a confidence multiplier on top of the LLM's verdict; nothing
is suppressed.
"""
from quodeq.context.path_role import NON_PROD_ROLES, Role, path_role

__all__ = ["NON_PROD_ROLES", "Role", "path_role"]
