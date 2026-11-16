"""npm install and build execution, source syncing, and directory helpers."""
from __future__ import annotations

import hashlib
import shutil
import time
from collections.abc import Mapping
from pathlib import Path

from quodeq.shared.env import env_int
from quodeq.shared.env_resolve import resolve_env
from quodeq.shared.logging import log_info

from quodeq.dashboard._build_hash import SYNC_ITEMS
from quodeq.shared.quiet_run import run_quiet
from quodeq.shared.win_launch import find_program

_UI_DIRNAME = "ui"  # bundled UI source directory name, both inside the package and in the repo

# Written into node_modules after a successful `npm ci`: the sha256 of the
# package-lock.json it installed, so an unchanged lockfile skips the install.
_INSTALL_STAMP = ".quodeq-lock-sha256"
_LOCKFILE = "package-lock.json"

_NPM_INSTALL_TIMEOUT_DEFAULT_S = 300  # QUODEQ_NPM_INSTALL_TIMEOUT_S fallback
_NPM_BUILD_TIMEOUT_DEFAULT_S = 600  # QUODEQ_NPM_BUILD_TIMEOUT_S fallback


def _npm_install_timeout_s(env: Mapping[str, str] | None = None) -> int:
    """Seconds allowed for ``npm ci``; ``QUODEQ_NPM_INSTALL_TIMEOUT_S`` overrides."""
    return env_int("QUODEQ_NPM_INSTALL_TIMEOUT_S", _NPM_INSTALL_TIMEOUT_DEFAULT_S, minimum=1, env=resolve_env(env))


def _npm_build_timeout_s(env: Mapping[str, str] | None = None) -> int:
    """Seconds allowed for ``npm run build``; ``QUODEQ_NPM_BUILD_TIMEOUT_S`` overrides."""
    return env_int("QUODEQ_NPM_BUILD_TIMEOUT_S", _NPM_BUILD_TIMEOUT_DEFAULT_S, minimum=1, env=resolve_env(env))


def quodeq_dir(env: Mapping[str, str] | None = None) -> Path:
    """Return the base Quodeq directory, overridable via QUODEQ_DIR env var."""
    return Path(resolve_env(env).get("QUODEQ_DIR", str(Path.home() / ".quodeq")))


def build_workdir() -> Path:
    return quodeq_dir() / "ui_build"


def default_static_dir() -> Path:
    return quodeq_dir() / "static"


def dev_static_dir() -> Path:
    return quodeq_dir() / "static-dev"


def dev_build_workdir() -> Path:
    return quodeq_dir() / "ui_build_dev"


def get_ui_source_dir() -> Path:
    """Return the path to the UI source bundled inside the package."""
    return Path(__file__).resolve().parent.parent / _UI_DIRNAME


def sync_source_to_workdir(source_dir: Path, workdir: Path) -> None:
    """Selectively copy source files to the build working directory.

    Preserves ``node_modules/`` in *workdir* if it already exists.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    for item_name in SYNC_ITEMS:
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


def _lock_digest(workdir: Path) -> str | None:
    lockfile = workdir / _LOCKFILE
    if not lockfile.is_file():
        return None
    return hashlib.sha256(lockfile.read_bytes()).hexdigest()


def dependencies_installed(workdir: Path) -> bool:
    """True when node_modules was installed from the current package-lock.json."""
    digest = _lock_digest(workdir)
    stamp = workdir / "node_modules" / _INSTALL_STAMP
    return digest is not None and stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == digest


def run_npm_build(
    workdir: Path, static_dir: Path, env: Mapping[str, str] | None = None,
    *, force_install: bool = False,
) -> None:
    """Run ``npm ci`` when the lockfile changed (or *force_install*), then ``npm run build``.

    *env* is the mapping the build's timeouts are read from and the base of
    the child process's environment; it defaults to ``os.environ``.
    """
    npm = find_program("npm")
    if npm is None:
        raise FileNotFoundError(
            "npm not found on PATH. Install Node.js from https://nodejs.org/ or via your package manager."
        )

    started = time.monotonic()
    if force_install or not dependencies_installed(workdir):
        log_info("Dependencies changed, reinstalling them...")
        # `npm ci` enforces lockfile-pinned installs (refuses to mutate
        # package-lock.json, errors if it's out of sync). `SYNC_ITEMS` in
        # `_build_hash.py` copies package-lock.json into the workdir before
        # this runs. `--no-audit` skips the live, uncached POST to the npm
        # advisories endpoint, which is purely informational here (it never
        # fails the install) but can blow past the timeout on slow networks.
        run_quiet(
            [npm, "ci", "--no-audit"], label="Gathering the building blocks", cwd=str(workdir),
            timeout=_npm_install_timeout_s(env),
        )
        digest = _lock_digest(workdir)
        if digest is not None:
            (workdir / "node_modules" / _INSTALL_STAMP).write_text(digest, encoding="utf-8")

    # QUODEQ_BUILD_QUIET skips Vite's gzip size report: nobody sees the
    # captured table, so computing it is wasted time.
    build_env = {
        **resolve_env(env), "QUODEQ_BUILD_OUTDIR": str(static_dir), "QUODEQ_BUILD_QUIET": "1",
    }
    run_quiet(
        [npm, "run", "build"], label="Building your dashboard to Quodeq standards", cwd=str(workdir),
        timeout=_npm_build_timeout_s(env), env=build_env,
    )
    log_info(f"Dashboard ready in {time.monotonic() - started:.1f}s. It passed its own review.")


def resolve_dev_source() -> Path:
    """Find the UI source directory for --dev mode (repo working copy)."""
    cwd = Path.cwd()
    for candidate in (cwd / _UI_DIRNAME / "web", cwd / "src" / "quodeq" / _UI_DIRNAME):
        if (candidate / "package.json").exists():
            return candidate
    for parent in cwd.parents:
        candidate = parent / _UI_DIRNAME / "web"
        if (candidate / "package.json").exists():
            return candidate
    raise FileNotFoundError(
        "Cannot find UI source directory. "
        "Run --dev from the quodeq repo root or a subdirectory."
    )
