#!/bin/bash
set -euo pipefail

# Build Quodeq.dmg for macOS — menu bar app
# Usage: ./packaging/macos/build-dmg.sh
# Prerequisites: brew install create-dmg (optional)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$REPO_ROOT/dist/macos-build"
DMG_DIR="$REPO_ROOT/dist"

VERSION=$(python3 -c "
import re
text = open('$REPO_ROOT/pyproject.toml').read()
print(re.search(r'version = \"(.+?)\"', text).group(1))
")
echo "Building Quodeq v$VERSION menu bar app..."

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR" "$DMG_DIR"

# Step 1: Bundle menu bar app with PyInstaller
echo "==> Building app bundle..."
export QUODEQ_REPO_ROOT="$REPO_ROOT"
uv run --with pyinstaller --with rumps pyinstaller \
    --name QuodeqBar \
    --windowed \
    --icon "$SCRIPT_DIR/icon.icns" \
    --osx-bundle-identifier com.quodeq.menubar \
    --distpath "$BUILD_DIR/dist" \
    --workpath "$BUILD_DIR/work" \
    --specpath "$BUILD_DIR" \
    --hidden-import rumps \
    --collect-all rumps \
    --add-data "$SCRIPT_DIR/icon.icns:." \
    --add-data "$SCRIPT_DIR/menubar_iconTemplate.png:." \
    --add-data "$SCRIPT_DIR/menubar_iconTemplate@2x.png:." \
    --add-data "$SCRIPT_DIR/menubar_icon_running.png:." \
    --add-data "$SCRIPT_DIR/menubar_icon_running@2x.png:." \
    --add-data "$SCRIPT_DIR/menubar_icon_evaluating.png:." \
    --add-data "$SCRIPT_DIR/menubar_icon_evaluating@2x.png:." \
    "$SCRIPT_DIR/menubar.py"

APP="$BUILD_DIR/dist/QuodeqBar.app"

if [ ! -d "$APP" ]; then
    echo "ERROR: Quodeq.app was not created."
    exit 1
fi

# Add Info.plist extras
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$APP/Contents/Info.plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $VERSION" "$APP/Contents/Info.plist" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VERSION" "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $VERSION" "$APP/Contents/Info.plist" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$APP/Contents/Info.plist"

# Copy icon to Resources
cp "$SCRIPT_DIR/icon.icns" "$APP/Contents/Resources/icon.icns"

echo "  Created $APP"

# Step 2: Create DMG
echo "==> Creating DMG..."
DMG_PATH="$DMG_DIR/QuodeqBar-${VERSION}-macOS.dmg"
rm -f "$DMG_PATH"

if command -v create-dmg &>/dev/null; then
    DMGOPTS=(
        --volname "Quodeq"
        --volicon "$SCRIPT_DIR/volicon.icns"
        --background "$SCRIPT_DIR/dmg-background.png"
        --window-pos 200 120
        --window-size 540 380
        --icon-size 100
        --text-size 13
        --icon "QuodeqBar.app" 150 180
        --hide-extension "QuodeqBar.app"
        --app-drop-link 390 180
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
