"""Immutable configuration types for the dashboard server."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServerConfig:
    """Network and API server settings."""
    port: int
    api_host: str | None = None
    api_port: int | None = None
    api_forced: bool = False


@dataclass(frozen=True)
class BuildConfig:
    """UI build and browser options."""
    open_browser: bool
    no_build: bool
    reinstall: bool


@dataclass(frozen=True)
class DashboardConfig:
    """Immutable configuration for the dashboard server (ports, paths, build options)."""
    server: ServerConfig
    build: BuildConfig
    reports_dir: Path
    static_dist: Path
    repo_root: Path
    reports_defaulted: bool = False

