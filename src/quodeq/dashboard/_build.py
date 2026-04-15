"""UI build helpers — copy source to cache, hash-based rebuild detection, npm build.

This module is the public entry point; implementation is split across
``_build_hash`` (hashing / rebuild detection) and ``_build_npm`` (npm execution).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from quodeq.shared.logging import log_info

# Re-exports so existing importers keep working
from quodeq.dashboard._build_hash import (  # noqa: F401
    _HASH_FILE,
    compute_source_hash,
    needs_rebuild,
)
from quodeq.dashboard._build_npm import (  # noqa: F401
    _build_workdir,
    _dev_build_workdir,
    _dev_static_dir,
    _get_ui_source_dir,
    _quodeq_dir,
    _static_dir,
    resolve_dev_source,
    run_npm_build,
    sync_source_to_workdir,
)


def maybe_build_ui(no_build: bool, reinstall: bool, dev: bool = False) -> Path:
    """Build the UI if needed and return the path to the static dist directory.

    Raises FileNotFoundError if --no-build is set and no cached build exists.
    """
    if dev:
        source_dir = resolve_dev_source()
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

    if not dev:
        bundled_static = source_dir.parent / "static"
        if (bundled_static / "index.html").exists():
            log_info("Updating cached UI from bundled build...")
            if static_dir.exists():
                shutil.rmtree(static_dir)
            shutil.copytree(bundled_static, static_dir)
            current_hash = compute_source_hash(source_dir)
            (static_dir / _HASH_FILE).write_text(current_hash)
            return static_dir

    log_info("Building web UI (source changed)...")
    if dev:
        workdir = source_dir
    else:
        workdir = _build_workdir()
        sync_source_to_workdir(source_dir, workdir)
    static_dir.mkdir(parents=True, exist_ok=True)
    run_npm_build(workdir, static_dir)

    current_hash = compute_source_hash(source_dir)
    (static_dir / _HASH_FILE).write_text(current_hash)

    return static_dir
