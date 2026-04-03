"""npm install and build execution, source syncing, and directory helpers."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from quodeq.shared.logging import log_info

_NPM_INSTALL_TIMEOUT_S = 300
_NPM_BUILD_TIMEOUT_S = 600


def _quodeq_dir(env: dict[str, str] | None = None) -> Path:
    """Return the base Quodeq directory, overridable via QUODEQ_DIR env var."""
    return Path((env if env is not None else os.environ).get("QUODEQ_DIR", str(Path.home() / ".quodeq")))


def _build_workdir() -> Path:
    return _quodeq_dir() / "ui_build"


def _static_dir() -> Path:
    return _quodeq_dir() / "static"


def _dev_static_dir() -> Path:
    return _quodeq_dir() / "static-dev"


def _dev_build_workdir() -> Path:
    return _quodeq_dir() / "ui_build_dev"


def _get_ui_source_dir() -> Path:
    """Return the path to the UI source bundled inside the package."""
    return Path(__file__).resolve().parent.parent / "ui"


# Files and directories to sync from package source to build workdir
_SYNC_ITEMS = ("src", "public", "package.json", "package-lock.json", ".npmrc", "vite.config.js", "index.html")


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
    return not (workdir / "node_modules").is_dir()


def _npm_cmd() -> str:
    """Resolve the npm executable path."""
    npm = shutil.which("npm")
    if npm is None:
        raise FileNotFoundError("npm not found on PATH")
    return npm


def run_npm_build(workdir: Path, static_dir: Path) -> None:
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


def resolve_dev_source() -> Path:
    """Find the UI source directory for --dev mode (repo working copy)."""
    cwd = Path.cwd()
    for candidate in (cwd / "ui" / "web", cwd / "src" / "quodeq" / "ui"):
        if (candidate / "package.json").exists():
            return candidate
    for parent in cwd.parents:
        candidate = parent / "ui" / "web"
        if (candidate / "package.json").exists():
            return candidate
    raise FileNotFoundError(
        "Cannot find UI source directory. "
        "Run --dev from the quodeq repo root or a subdirectory."
    )
