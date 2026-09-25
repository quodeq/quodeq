"""Injectable dependency bundle for the shared-repo connect/disconnect use cases.

Leaf module: imports only under ``TYPE_CHECKING``, so it can be imported by
both ``shared_connect.py`` and ``shared_repo.py`` without pulling in either
(same rationale as ``scoring_deps.ScoringDeps``). A ``None`` field resolves
to the production callable at call time, so the seam is purely additive --
existing callers pass nothing and see no change.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from contextlib import AbstractContextManager
    from pathlib import Path

    from quodeq.services.shared_settings import SharedSettings
    from quodeq.services.wiring import RepoFormat


@dataclass(frozen=True)
class SharedRepoOps:
    """Clone/settings collaborators the shared-repo connect/disconnect use cases drive."""

    validate: Callable[[str], None] | None = None
    read_state: Callable[[str], "RepoFormat"] | None = None
    ensure_clone: Callable[[str], object] | None = None
    refresh_clone: Callable[[str], object] | None = None
    check_format: Callable[[object], "RepoFormat"] | None = None
    read_settings: Callable[[], "SharedSettings"] | None = None
    write_settings: Callable[..., None] | None = None
    clone_lock: Callable[[str], "AbstractContextManager"] | None = None
    remove_clone_dir: Callable[["Path"], None] | None = None
    shared_cache_dir: Callable[[str], "Path"] | None = None


NO_OPS = SharedRepoOps()
