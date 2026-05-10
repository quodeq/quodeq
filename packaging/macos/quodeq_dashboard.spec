# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Quodeq Dashboard macOS .app bundle."""

import os
import sys
from pathlib import Path

repo_root = Path(os.environ["QUODEQ_REPO_ROOT"])
src_dir = repo_root / "src"
pkg_dir = repo_root / "packaging" / "macos"

# ── Data files ──
datas = []

data_dir = src_dir / "quodeq" / "data"
if data_dir.exists():
    datas.append((str(data_dir), "quodeq/data"))

static_dir = src_dir / "quodeq" / "static"
if static_dir.exists():
    datas.append((str(static_dir), "quodeq/static"))

defaults_json = src_dir / "quodeq" / "shared" / "defaults.json"
if defaults_json.exists():
    datas.append((str(defaults_json), "quodeq/shared"))

# Schema files for validation
schemas_dir = src_dir / "quodeq" / "analysis" / "plugins" / "schemas"
if schemas_dir.exists():
    datas.append((str(schemas_dir), "quodeq/analysis/plugins/schemas"))

# AI config defaults
ai_defaults = src_dir / "quodeq" / "config" / "ai_defaults.json"
if ai_defaults.exists():
    datas.append((str(ai_defaults), "quodeq/config"))

# Icons live in src/quodeq/data/icons/ (already bundled via data_dir above);
# keep a local pointer for the BUNDLE() icon= arg below.
icon_icns = src_dir / "quodeq" / "data" / "icons" / "icon.icns"

# ── Analysis ──
a = Analysis(
    [str(pkg_dir / "dashboard_entry.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # quodeq — CLI and dashboard
        "quodeq.cli",
        "quodeq.cli_parser",
        "quodeq.dashboard.cli",
        "quodeq.dashboard._webview_window",
        "quodeq.dashboard._instance",
        "quodeq.dashboard._frozen",
        "quodeq.dashboard._server",
        "quodeq.dashboard._build_npm",
        # quodeq — API
        "quodeq.api.app",
        "quodeq.api.routes",
        "quodeq.api.routes_registry",
        "quodeq.api.helpers",
        # quodeq — services
        "quodeq.services.filesystem",
        "quodeq.services.jobs",
        "quodeq.services.accumulated",
        "quodeq.services.dashboard",
        "quodeq.services.rescore",
        "quodeq.services.dismissed",
        "quodeq.services.evaluation_mixin",
        # quodeq — analysis pipeline
        "quodeq.analysis.runner",
        "quodeq.analysis.subprocess",
        "quodeq.analysis._pipeline",
        "quodeq.analysis._command",
        "quodeq.analysis._process",
        "quodeq.analysis._config",
        "quodeq.analysis._provider_cache",
        "quodeq.analysis.plugins.schema_validator",
        # quodeq — core
        "quodeq.core.scoring.engine",
        "quodeq.core.scoring.report",
        "quodeq.core.scoring.overall",
        "quodeq.core.scoring.internals",
        "quodeq.core.scoring._principle",
        "quodeq.core.scoring._tallies",
        "quodeq.core.types",
        # quodeq — config and shared
        "quodeq.config.ai_provider",
        "quodeq.config._env_loader",
        "quodeq.shared.prereqs",
        "quodeq.shared.utils",
        "quodeq.shared._env",
        # dependencies
        "flask",
        "jsonschema",
        "webview",
        "webview.platforms.cocoa",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Quodeq",
    debug=False,
    strip=True,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=False,
    name="Quodeq",
)

app = BUNDLE(
    coll,
    name="Quodeq.app",
    icon=str(icon_icns) if icon_icns.exists() else None,
    bundle_identifier="com.quodeq.app",
    info_plist={
        "CFBundleShortVersionString": os.environ.get("QUODEQ_VERSION", "1.0.0b1"),
        "CFBundleVersion": os.environ.get("QUODEQ_VERSION", "1.0.0b1"),
        "CFBundleDisplayName": "Quodeq",
        "CFBundleName": "Quodeq",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
        "LSBackgroundOnly": False,
    },
)
