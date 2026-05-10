# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Quodeq macOS .app bundle."""

import os
import sys
from pathlib import Path

repo_root = Path(os.environ["QUODEQ_REPO_ROOT"])
src_dir = repo_root / "src"

# Collect the bundled data directory (evaluators, prompts, standards, config, static)
data_dir = src_dir / "quodeq" / "data"
static_dir = src_dir / "quodeq" / "static"
shared_dir = src_dir / "quodeq" / "shared"

datas = []
if data_dir.exists():
    datas.append((str(data_dir), "quodeq/data"))
if static_dir.exists():
    datas.append((str(static_dir), "quodeq/static"))
# Include defaults.json from shared/
defaults_json = shared_dir / "defaults.json"
if defaults_json.exists():
    datas.append((str(defaults_json), "quodeq/shared"))

a = Analysis(
    [str(repo_root / "packaging" / "macos" / "entry.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "quodeq.cli",
        "quodeq.dashboard.cli",
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
        "flask",
        "jsonschema",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="quodeq",
    debug=False,
    strip=True,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=False,
    name="quodeq",
)

app = BUNDLE(
    coll,
    name="Quodeq.app",
    icon=str(repo_root / "src" / "quodeq" / "data" / "icons" / "icon.icns") if (repo_root / "src" / "quodeq" / "data" / "icons" / "icon.icns").exists() else None,
    bundle_identifier="com.quodeq.app",
    info_plist={
        "CFBundleShortVersionString": os.environ.get("QUODEQ_VERSION", "0.6.2"),
        "CFBundleVersion": os.environ.get("QUODEQ_VERSION", "0.6.2"),
        "CFBundleDisplayName": "Quodeq",
        "CFBundleName": "Quodeq",
        "NSHighResolutionCapable": True,
        "LSBackgroundOnly": False,
    },
)
