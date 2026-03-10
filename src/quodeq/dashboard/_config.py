"""Immutable configuration types for the dashboard server."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quodeq.shared.utils import DEFAULT_HOST


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

    # Convenience accessors for backward compatibility
    @property
    def port(self) -> int:
        return self.server.port

    @property
    def open_browser(self) -> bool:
        return self.build.open_browser

    @property
    def no_build(self) -> bool:
        return self.build.no_build

    @property
    def reinstall(self) -> bool:
        return self.build.reinstall

    @property
    def api_host(self) -> str | None:
        return self.server.api_host

    @property
    def api_port(self) -> int | None:
        return self.server.api_port

    @property
    def api_forced(self) -> bool:
        return self.server.api_forced
