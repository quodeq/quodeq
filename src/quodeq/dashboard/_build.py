"""UI build helpers for the dashboard runner."""
from __future__ import annotations

import subprocess
from pathlib import Path

from quodeq.shared.logging import log_info


def npm_build(path: Path) -> None:
    """Run npm install and build in the given directory."""
    subprocess.run(["npm", "install"], cwd=str(path), check=True)
    subprocess.run(["npm", "run", "build"], cwd=str(path), check=True)


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
    dist_index = static_dist / "index.html"
    if reinstall or sources_newer_than_dist(repo_root / "ui/web", dist_index):
        log_info("Building web UI (ui/web)...")
        npm_build(repo_root / "ui/web")
    else:
        log_info("Web UI is up to date, skipping build.")
