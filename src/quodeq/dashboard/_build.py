"""UI build helpers — copy source to cache, hash-based rebuild detection, npm build."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from quodeq.shared.logging import log_debug, log_info

_HASH_FILE = ".build_hash"


def _quodeq_dir(env: dict[str, str] | None = None) -> Path:
    """Return the base Quodeq directory, overridable via QUODEQ_DIR env var."""
    return Path((env if env is not None else os.environ).get("QUODEQ_DIR", str(Path.home() / ".quodeq")))


def _build_workdir() -> Path:
    return _quodeq_dir() / "ui_build"


def _static_dir() -> Path:
    return _quodeq_dir() / "static"

# Files and directories to sync from package source to build workdir
_SYNC_ITEMS = ("src", "public", "package.json", "package-lock.json", ".npmrc", "vite.config.js", "index.html")

_NPM_INSTALL_TIMEOUT_S = 300
_NPM_BUILD_TIMEOUT_S = 600


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
        try:
            h.update(str(rel).encode())
            h.update(f.read_bytes())
        except OSError as exc:
            log_debug(f"Skipping {f.name} in source hash: {exc}")
            continue
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
        subprocess.run([npm, "install"], cwd=str(workdir), check=True, timeout=_NPM_INSTALL_TIMEOUT_S)
    else:
        log_info("npm dependencies up to date, skipping install.")

    log_info("Building web UI...")
    env = {**os.environ, "QUODEQ_BUILD_OUTDIR": str(static_dir)}
    subprocess.run([npm, "run", "build"], cwd=str(workdir), check=True, timeout=_NPM_BUILD_TIMEOUT_S, env=env)


def _resolve_dev_source() -> Path:
    """Find the UI source directory for --dev mode (repo working copy)."""
    # Look for ui/web/ relative to cwd, then walk up to find repo root
    cwd = Path.cwd()
    for candidate in (cwd / "ui" / "web", cwd / "src" / "quodeq" / "ui"):
        if (candidate / "package.json").exists():
            return candidate
    # Walk up looking for ui/web/
    for parent in cwd.parents:
        candidate = parent / "ui" / "web"
        if (candidate / "package.json").exists():
            return candidate
    raise FileNotFoundError(
        "Cannot find UI source directory. "
        "Run --dev from the quodeq repo root or a subdirectory."
    )


def _dev_static_dir() -> Path:
    return _quodeq_dir() / "static-dev"


def _dev_build_workdir() -> Path:
    return _quodeq_dir() / "ui_build_dev"


def maybe_build_ui(no_build: bool, reinstall: bool, dev: bool = False) -> Path:
    """Build the UI if needed and return the path to the static dist directory.

    Raises FileNotFoundError if --no-build is set and no cached build exists.
    """
    if dev:
        source_dir = _resolve_dev_source()
        static_dir = _dev_static_dir()
        log_info(f"Dev mode: building from {source_dir}")
    else:
        source_dir = _get_ui_source_dir()
        static_dir = _static_dir()

    if no_build:
        if not (static_dir / "index.html").exists():
            raise FileNotFoundError(
                f"No cached dashboard build found at {static_dir}.\n"
                "Run `quodeq dashboard` without --no-build first."
            )
        return static_dir

    if not dev and not needs_rebuild(source_dir, static_dir, reinstall):
        log_info("Web UI is up to date, skipping build.")
        return static_dir

    log_info("Building web UI (source changed)...")
    if dev:
        # Build directly from repo source — no copy needed
        workdir = source_dir
    else:
        workdir = _build_workdir()
        sync_source_to_workdir(source_dir, workdir)
    static_dir.mkdir(parents=True, exist_ok=True)
    _run_npm_build(workdir, static_dir)

    # Write content hash
    current_hash = compute_source_hash(source_dir)
    (static_dir / _HASH_FILE).write_text(current_hash)

    return static_dir
