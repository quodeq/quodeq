"""Scan metadata types for the quick-scan phase."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ScanData:
    """Result of a quick project scan (no AI evaluation)."""

    file_tree: list[str] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)
    branches: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    scanned_at: str = ""
    total_files: int = 0
    # Subset of total_files whose extension is recognised as analysable
    # source code (matches the language ext-map used by the evaluation).
    code_files: int = 0
