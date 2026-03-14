"""UI build helpers for the dashboard runner."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from quodeq.shared.logging import log_info

_MIN_NPM_MAJOR = 8


def _check_npm() -> None:
    """Raise RuntimeError if npm is not found or is below the minimum version."""
    try:
        use_shell = sys.platform == "win32"
        result = subprocess.run(
            ["npm", "--version"], capture_output=True, text=True, check=True, shell=use_shell,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("npm not found; install Node.js before building the UI.") from exc
    version_str = result.stdout.strip()
    try:
        major = int(version_str.split(".")[0])
    except (ValueError, IndexError):
        return  # unparseable version — let npm fail naturally
    if major < _MIN_NPM_MAJOR:
        raise RuntimeError(
            f"npm {version_str} is below the minimum required version {_MIN_NPM_MAJOR}.x."
        )


def npm_build(path: Path) -> None:
    """Run npm install and build in the given directory."""
    _check_npm()
    use_shell = sys.platform == "win32"
    subprocess.run(["npm", "install"], cwd=str(path), check=True, shell=use_shell)
    subprocess.run(["npm", "run", "build"], cwd=str(path), check=True, shell=use_shell)


def sources_newer_than_dist(web_root: Path, dist_index: Path) -> bool:
    """Return True if any tracked source file is newer than dist/index.html."""
    if not dist_index.exists():
        return True
    dist_mtime = dist_index.stat().st_mtime
    watch_dirs = [web_root / "src", web_root / "public"]
    watch_files = [web_root / "package.json", web_root / "vite.config.js"]
    for watch_file in watch_files:
        if watch_file.exists() and watch_file.stat().st_mtime > dist_mtime:
            return True
    for watch_dir in watch_dirs:
        if not watch_dir.exists():
            continue
        for watch_file in watch_dir.rglob("*"):
            if watch_file.is_file() and watch_file.stat().st_mtime > dist_mtime:
                return True
    return False


def maybe_build_ui(no_build: bool, reinstall: bool, static_dist: Path, repo_root: Path) -> None:
    """Run npm build if sources are newer than the dist."""
    if no_build:
        return
    # Skip build when serving pre-built bundled assets (pip install)
    web_source = repo_root / "ui" / "web"
    if not web_source.is_dir():
        log_info("Using bundled static assets (no ui/web source found).")
        return
    dist_index = static_dist / "index.html"
    if reinstall or sources_newer_than_dist(web_source, dist_index):
        log_info("Building web UI (ui/web)...")
        npm_build(web_source)
    else:
        log_info("Web UI is up to date, skipping build.")
