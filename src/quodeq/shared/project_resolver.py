"""Re-export shim — canonical location is quodeq.data.fs.project_resolver."""
from quodeq.data.fs.project_resolver import (
    ProjectIdentity,
    ProjectRepository,
    clear_index_cache,
    resolve_project_uuid,
)

__all__ = [
    "ProjectIdentity",
    "ProjectRepository",
    "clear_index_cache",
    "resolve_project_uuid",
]
