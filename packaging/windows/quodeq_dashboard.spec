# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Quodeq Dashboard Windows .exe bundle."""

import os
import sys
from pathlib import Path

repo_root = Path(os.environ["QUODEQ_REPO_ROOT"])
src_dir = repo_root / "src"
pkg_mac = repo_root / "packaging" / "macos"
pkg_win = repo_root / "packaging" / "windows"

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
icon_ico = pkg_win / "icon.ico"
if icon_ico.exists():
    datas.append((str(icon_ico), "packaging/windows"))

icon_icns = pkg_mac / "icon.icns"
if icon_icns.exists():
    datas.append((str(icon_icns), "packaging/macos"))

# ── Analysis ──
a = Analysis(
    [str(pkg_mac / "dashboard_entry.py")],
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
        "webview.platforms.edgechromium",
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
    strip=False,
    upx=False,
    console=False,
    icon=str(icon_ico) if icon_ico.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Quodeq",
)
