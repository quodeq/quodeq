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

# Bundle icons so _icon_path() finds them in frozen mode
icon_icns = pkg_dir / "icon.icns"
if icon_icns.exists():
    datas.append((str(icon_icns), "packaging/macos"))

icon_ico = repo_root / "packaging" / "windows" / "icon.ico"
if icon_ico.exists():
    datas.append((str(icon_ico), "packaging/windows"))

# ── Analysis ──
a = Analysis(
    [str(pkg_dir / "dashboard_entry.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # quodeq modules
        "quodeq.cli",
        "quodeq.dashboard.cli",
        "quodeq.dashboard._webview_window",
        "quodeq.dashboard._instance",
        "quodeq.dashboard._frozen",
        "quodeq.api.app",
        "quodeq.api.routes",
        "quodeq.services.filesystem",
        "quodeq.services.jobs",
        "quodeq.services.accumulated",
        "quodeq.services.dashboard",
        "quodeq.analysis.runner",
        "quodeq.analysis.subprocess",
        "quodeq.core.scoring.engine",
        "quodeq.core.scoring.report",
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
