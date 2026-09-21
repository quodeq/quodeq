"""Repo browsing for the filesystem action provider: list, validate, mkdir.

Split from ``tooling_mixin.py``, which now holds only AI-client and model
discovery. ``FsToolingMixin`` inherits from the class here, so every caller
still reaches ``browse_repo``/``browse_mkdir`` through the one collaborator
``FilesystemActionProvider`` holds.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from quodeq.data.fs.report_parser import safe_read_dir
from quodeq.services._browse_entries import readable_entries

_BROWSE_DIR_LIMIT = 500


class FsBrowseMixin:
    """Home-rooted directory browsing: the provider never leaves ``~``."""

    @staticmethod
    def _validate_browse_path(path: str | None) -> tuple[Path, dict[str, Any] | None]:
        """Resolve and validate a browse path. Returns (target, error_or_None)."""
        target = Path(path) if path else Path.home()
        target = target.resolve()
        if not target.is_relative_to(Path.home().resolve()):
            return target, {"error": "Path outside allowed boundary", "error_code": "PATH_OUTSIDE_BOUNDARY"}
        if not target.exists():
            return target, {"error": "Path not found", "error_code": "PATH_NOT_FOUND", "path": str(target)}
        if not target.is_dir():
            return target, {"error": "Path is not a directory", "error_code": "PATH_NOT_DIRECTORY", "path": str(target)}
        return target, None

    @staticmethod
    def _list_directories(
        target: Path, entries: list[os.DirEntry[str]] | None = None,
    ) -> list[dict[str, Any]]:
        """List readable non-hidden subdirectories of *target*.

        *entries* supplies an already-read listing so a caller that also needs
        the files does not pay for a second scandir.
        """
        directories = [
            {
                "name": entry.name,
                "path": str(entry_path),
                "isGitRepo": (entry_path / ".git").exists(),
            }
            for entry, entry_path in readable_entries(target, entries, want_dirs=True)
        ]
        directories.sort(key=lambda item: item["name"])
        return directories

    @staticmethod
    def _list_files(
        target: Path, entries: list[os.DirEntry[str]] | None = None,
    ) -> list[dict[str, Any]]:
        """List readable non-hidden source files in *target*.

        *entries* supplies an already-read listing, as in ``_list_directories``.
        """
        files: list[dict[str, Any]] = [
            {"name": entry.name, "path": str(entry_path)}
            for entry, entry_path in readable_entries(target, entries, want_dirs=False)
        ]
        files.sort(key=lambda item: item["name"])
        return files

    @staticmethod
    def _build_browse_response(
        target: Path, directories: list[dict[str, Any]],
        files: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Assemble a browse_repo response from a validated target and directory list."""
        truncated = len(directories) > _BROWSE_DIR_LIMIT
        if truncated:
            directories = directories[:_BROWSE_DIR_LIMIT]
        parent = target.parent if target.parent != target else None
        response: dict[str, Any] = {
            "current": str(target),
            "parent": str(parent) if parent else None,
            "directories": directories,
            "isGitRepo": (target / ".git").exists(),
            "truncated": truncated,
        }
        if files is not None:
            response["files"] = files
        return response

    def browse_repo(self, path: str | None, include_files: bool = False) -> dict[str, Any]:
        """List directories (and optionally files) at the given path.

        Single-pass traversal: the directory is read once and the same entries
        feed both listing helpers, avoiding redundant filesystem scans.
        """
        target, error = self._validate_browse_path(path)
        if error is not None:
            return error
        entries = safe_read_dir(target)
        directories = self._list_directories(target, entries)
        files = self._list_files(target, entries) if include_files else None
        return self._build_browse_response(target, directories, files)

    def browse_mkdir(self, parent: str, name: str) -> dict[str, Any]:
        """Create subdirectory *name* under *parent* (jailed to the home dir).

        Owns the full validation policy so the route only maps error codes
        onto HTTP statuses: field presence, folder-name shape, the same
        home jail as ``browse_repo``, parent existence, and the mkdir
        itself (never with parents — a missing parent is a caller error).
        """
        if not parent or not name:
            return {"error": "path and name are required", "error_code": "MISSING_FIELDS"}
        if "/" in name or "\\" in name or name in (".", ".."):
            return {"error": "Invalid folder name", "error_code": "INVALID_NAME"}
        resolved = Path(parent).resolve()
        home = Path.home().resolve()
        if not resolved.is_relative_to(home):
            return {
                "error": "Path must be within the user's home directory",
                "error_code": "PATH_OUTSIDE_BOUNDARY",
            }
        if not resolved.is_dir():
            return {"error": "Parent path not found", "error_code": "PARENT_NOT_FOUND"}
        target = resolved / name
        try:
            target.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            return {"error": "Folder already exists", "error_code": "ALREADY_EXISTS"}
        except OSError as exc:
            _logger.warning("Could not create folder %s: %s", name, exc)
            return {"error": "Could not create folder", "error_code": "MKDIR_FAILED"}
        return {"created": True, "path": str(target)}

    # Default AI CLI candidates. Override via the QUODEQ_AI_CLIENTS env var
    # (comma-separated list of client IDs, e.g. "claude,codex").
    _CLI_CANDIDATES = [
        {"id": "claude", "label": "Claude"}, {"id": "codex", "label": "Codex"},
        {"id": "gemini", "label": "Gemini"}, {"id": "copilot", "label": "GitHub Copilot"},
    ]
