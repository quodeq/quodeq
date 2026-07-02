"""Shared per-session context handed to every tool handler."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quodeq.data.sqlite.assistant_repository import AssistantRepository


@dataclass(frozen=True)
class ToolContext:
    repository: AssistantRepository
    session_id: str
    run_dir: Path | None
    repo_root: Path | None
    evaluators_dir: Path
    compiled_dir: Path
    dimensions_file: Path
