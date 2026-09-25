"""Re-export shim: project-identity import helpers now live in
``services/project_import_identity.py`` (SEP-03: the API layer must not walk
directories or parse/rewrite ``repository_info.json`` itself).

Kept for ``tests/api/test_import_identity.py``'s existing import path;
production code (``api/import_project.py``) imports from the new home
directly.
"""
from __future__ import annotations

from quodeq.services.project_import_identity import (
    REPO_INFO_FILENAME,
    find_identity_collision,
    identity_from_info,
    rewrite_repository_info,
    update_index,
)

__all__ = [
    "REPO_INFO_FILENAME",
    "find_identity_collision",
    "identity_from_info",
    "rewrite_repository_info",
    "update_index",
]
