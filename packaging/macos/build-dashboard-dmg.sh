#!/bin/bash
set -euo pipefail

# Build Quodeq.dmg for macOS — standalone dashboard app
# Usage: ./packaging/macos/build-dashboard-dmg.sh
# Prerequisites: brew install create-dmg (optional, for styled DMG)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$REPO_ROOT/dist/dashboard-build"
DMG_DIR="$REPO_ROOT/dist"

# DMG layout settings
DMG_WINDOW_X=200
DMG_WINDOW_Y=120
DMG_WINDOW_WIDTH=540
DMG_WINDOW_HEIGHT=380
DMG_ICON_SIZE=100
DMG_TEXT_SIZE=13
DMG_APP_ICON_X=150
DMG_APP_ICON_Y=180
DMG_DROP_LINK_X=390
DMG_DROP_LINK_Y=180

VERSION=$(python3 -c "
import re
text = open('$REPO_ROOT/pyproject.toml').read()
print(re.search(r'version = \"(.+?)\"', text).group(1))
")
echo "Building Quodeq v$VERSION..."

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR" "$DMG_DIR"

# Step 1: Build web UI (always fresh to avoid stale asset hashes)
# Vite outputs directly to src/quodeq/static/ via its config
STATIC_DIR="$REPO_ROOT/src/quodeq/static"
rm -rf "$STATIC_DIR"
echo "==> Building web UI..."
cd "$REPO_ROOT/src/quodeq/ui" && npm ci && npm run build
cd "$REPO_ROOT"

# Step 2: Bundle with PyInstaller
echo "==> Building app bundle..."
export QUODEQ_REPO_ROOT="$REPO_ROOT"
export QUODEQ_VERSION="$VERSION"
uv run --with pyinstaller --with pywebview --with flask --with jsonschema pyinstaller \
    "$SCRIPT_DIR/quodeq_dashboard.spec" \
    --distpath "$BUILD_DIR/dist" \
    --workpath "$BUILD_DIR/work"

APP="$BUILD_DIR/dist/Quodeq.app"

if [ ! -d "$APP" ]; then
    echo "ERROR: Quodeq.app was not created."
    exit 1
fi

echo "  Created $APP"

# Step 3: Strip quarantine attribute so users don't need xattr -cr
xattr -cr "$APP"

# Step 4: Create DMG
echo "==> Creating DMG..."
DMG_PATH="$DMG_DIR/Quodeq-${VERSION}-macOS.dmg"
rm -f "$DMG_PATH"

if command -v create-dmg &>/dev/null; then
    DMGOPTS=(
        --volname "Quodeq"
        --volicon "$SCRIPT_DIR/volicon.icns"
        --background "$SCRIPT_DIR/dmg-background.png"
        --window-pos "$DMG_WINDOW_X" "$DMG_WINDOW_Y"
        --window-size "$DMG_WINDOW_WIDTH" "$DMG_WINDOW_HEIGHT"
        --icon-size "$DMG_ICON_SIZE"
        --text-size "$DMG_TEXT_SIZE"
        --icon "Quodeq.app" "$DMG_APP_ICON_X" "$DMG_APP_ICON_Y"
        --hide-extension "Quodeq.app"
        --app-drop-link "$DMG_DROP_LINK_X" "$DMG_DROP_LINK_Y"
        --no-internet-enable
    )
    create-dmg "${DMGOPTS[@]}" "$DMG_PATH" "$APP" || true
else
    hdiutil create -volname "Quodeq $VERSION" \
        -srcfolder "$APP" \
        -ov -format UDZO \
        "$DMG_PATH"
fi

if [ -f "$DMG_PATH" ]; then
    SIZE=$(du -h "$DMG_PATH" | cut -f1)
    echo ""
    echo "==> Done: $DMG_PATH ($SIZE)"
else
    echo "ERROR: DMG was not created."
    exit 1
fi
