"""UI build helpers — production reads bundled static, dev rebuilds from source.

Production installs ship a pre-built UI inside the wheel (see
``pyproject.toml``'s ``wheel-exclude``). End users never invoke npm at
runtime. The ``--dev`` codepath keeps the source-aware rebuild loop for
contributors working out of the repo.

This module is the public entry point; implementation is split across
``_build_hash`` (hashing / rebuild detection) and ``_build_npm`` (npm
execution, dev-only).
"""
from __future__ import annotations

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


def _static_dir_bundled() -> Path:
    """Path to the wheel-bundled static dist directory.

    In an installed wheel this is ``<site-packages>/quodeq/static/``.
    When running from a source checkout it resolves to
    ``src/quodeq/static/`` (populated by ``tools/build-dist.sh`` or
    ``npm run build``).
    """
    return Path(__file__).resolve().parent.parent / "static"


def maybe_build_ui(no_build: bool, reinstall: bool, dev: bool = False) -> Path:
    """Return the static dist directory, building if necessary (dev mode only).

    Production mode (``dev=False``) reads the wheel-bundled static dir and
    never invokes npm. Missing static raises ``FileNotFoundError`` with
    installation guidance instead of falling back to a silent rebuild.

    Dev mode (``dev=True``) keeps the legacy behavior: resolve the repo
    source, rebuild via ``run_npm_build`` when ``needs_rebuild`` says so,
    or honor ``--no-build`` if the user wants to reuse the cached build.

    Raises ``FileNotFoundError`` when:
      - production: bundled ``static/index.html`` is absent
      - dev + ``no_build=True``: no cached ``static-dev/index.html`` exists
    """
    if dev:
        source_dir = resolve_dev_source()
        static_dir = _dev_static_dir()
        log_info(f"Dev mode: building from {source_dir}")

        if no_build:
            if not (static_dir / "index.html").exists():
                raise FileNotFoundError(
                    f"No cached dashboard build found at {static_dir}.\n"
                    "Run `quodeq dashboard --dev` without --no-build first."
                )
            return static_dir

        if not needs_rebuild(source_dir, static_dir, reinstall):
            log_info("Web UI is up to date, skipping build.")
            return static_dir

        log_info("Building web UI (source changed)...")
        static_dir.mkdir(parents=True, exist_ok=True)
        run_npm_build(source_dir, static_dir)
        (static_dir / _HASH_FILE).write_text(compute_source_hash(source_dir))
        return static_dir

    # Production: the wheel ships a pre-built UI. Never invoke npm here.
    static_dir = _static_dir_bundled()
    if not (static_dir / "index.html").exists():
        raise FileNotFoundError(
            "UI static assets are missing from the installed quodeq package.\n"
            "This usually means the wheel was built without running the UI build first.\n"
            "  If you installed via pipx/pip: try `pipx reinstall quodeq` "
            "(or `pip install --force-reinstall quodeq`).\n"
            "  If you built locally from source: run `tools/build-dist.sh` "
            "(which builds the UI before packaging) instead of `uv build` directly."
        )
    return static_dir
