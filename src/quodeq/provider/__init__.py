"""Action provider bounded context — interfaces, filesystem implementation, and supporting services.

Public API:
    ActionProvider      — composite protocol all providers must satisfy.
    EvaluationOptions   — value object for evaluation run options.
    FilesystemActionProvider — concrete provider backed by the local filesystem.
    JobManager          — background subprocess lifecycle manager.
"""

from quodeq.provider.base import ActionProvider, EvaluationOptions
from quodeq.provider.filesystem import FilesystemActionProvider
from quodeq.provider.jobs import JobManager

__all__ = [
    "ActionProvider",
    "EvaluationOptions",
    "FilesystemActionProvider",
    "JobManager",
]
