"""UI build helpers — copy source to cache, hash-based rebuild detection, npm build."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from quodeq.shared.logging import log_info
from quodeq.shared.utils import IS_WIN32 as _IS_WIN32

_HASH_FILE = ".build_hash"
_QUODEQ_DIR = Path.home() / ".quodeq"
_BUILD_WORKDIR = _QUODEQ_DIR / "ui_build"
_STATIC_DIR = _QUODEQ_DIR / "static"

# Files and directories to sync from package source to build workdir
_SYNC_ITEMS = ("src", "public", "package.json", "vite.config.js", "index.html")


def _get_ui_source_dir() -> Path:
    """Return the path to the UI source bundled inside the package."""
    return Path(__file__).resolve().parent.parent / "ui"


def compute_source_hash(source_dir: Path) -> str:
    """Compute a SHA-256 hash over all tracked source files."""
    h = hashlib.sha256()
    files: list[Path] = []
    for item_name in _SYNC_ITEMS:
        item = source_dir / item_name
        if item.is_file():
            files.append(item)
        elif item.is_dir():
            files.extend(sorted(f for f in item.rglob("*") if f.is_file()))
    for f in sorted(files):
        rel = f.relative_to(source_dir)
        h.update(str(rel).encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def needs_rebuild(source_dir: Path, static_dir: Path, reinstall: bool) -> bool:
    """Return True if the UI needs to be rebuilt."""
    if reinstall:
        return True
    if not (static_dir / "index.html").exists():
        return True
    hash_file = static_dir / _HASH_FILE
    if not hash_file.exists():
        return True
    stored_hash = hash_file.read_text().strip()
    current_hash = compute_source_hash(source_dir)
    return stored_hash != current_hash


def sync_source_to_workdir(source_dir: Path, workdir: Path) -> None:
    """Selectively copy source files to the build working directory.

    Preserves ``node_modules/`` in *workdir* if it already exists.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    for item_name in _SYNC_ITEMS:
        src_item = source_dir / item_name
        dst_item = workdir / item_name
        if not src_item.exists():
            continue
        if src_item.is_dir():
            if dst_item.exists():
                shutil.rmtree(dst_item)
            shutil.copytree(src_item, dst_item)
        else:
            shutil.copy2(src_item, dst_item)


def _needs_npm_install(workdir: Path) -> bool:
    """Return True if npm install is needed (node_modules missing)."""
    if not (workdir / "node_modules").is_dir():
        return True
    return False


def _npm_cmd() -> str:
    """Resolve the npm executable path."""
    npm = shutil.which("npm")
    if npm is None:
        raise FileNotFoundError("npm not found on PATH")
    return npm


def _run_npm_build(workdir: Path, static_dir: Path) -> None:
    """Run npm install (if needed) and npm run build."""
    npm = _npm_cmd()

    if _needs_npm_install(workdir):
        log_info("Installing npm dependencies...")
        subprocess.run([npm, "install"], cwd=str(workdir), check=True, timeout=300)
    else:
        log_info("npm dependencies up to date, skipping install.")

    log_info("Building web UI...")
    env = {**os.environ, "QUODEQ_BUILD_OUTDIR": str(static_dir)}
    subprocess.run([npm, "run", "build"], cwd=str(workdir), check=True, timeout=600, env=env)


def maybe_build_ui(no_build: bool, reinstall: bool) -> Path:
    """Build the UI if needed and return the path to the static dist directory.

    Raises FileNotFoundError if --no-build is set and no cached build exists.
    """
    static_dir = _STATIC_DIR
    source_dir = _get_ui_source_dir()

    if no_build:
        if not (static_dir / "index.html").exists():
            raise FileNotFoundError(
                f"No cached dashboard build found at {static_dir}.\n"
                "Run `quodeq dashboard` without --no-build first."
            )
        return static_dir

    if not needs_rebuild(source_dir, static_dir, reinstall):
        log_info("Web UI is up to date, skipping build.")
        return static_dir

    log_info("Building web UI (source changed)...")
    workdir = _BUILD_WORKDIR
    sync_source_to_workdir(source_dir, workdir)
    static_dir.mkdir(parents=True, exist_ok=True)
    _run_npm_build(workdir, static_dir)

    # Write content hash
    current_hash = compute_source_hash(source_dir)
    (static_dir / _HASH_FILE).write_text(current_hash)

    return static_dir
