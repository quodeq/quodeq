#!/usr/bin/env bash
# Build the full quodeq package (frontend + backend).
# Usage: ./scripts/build.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UI_WEB="$ROOT/ui/web"
STATIC_DEST="$ROOT/src/quodeq/static"

echo "==> Building frontend..."
(cd "$UI_WEB" && npm install && npm run build)

echo "==> Bundling frontend into package..."
rm -rf "$STATIC_DEST"
cp -r "$UI_WEB/dist" "$STATIC_DEST"

echo "==> Syncing engine_version in plugin files..."
VERSION=$(python3 -c "import tomllib; print(tomllib.load(open('$ROOT/pyproject.toml','rb'))['project']['version'])")
ENGINE_VERSION_PATTERN='"engine_version": "==[^"]*"'
ENGINE_VERSION_REPLACE="\"engine_version\": \"==$VERSION\""
find "$ROOT/evaluators" "$ROOT/tests" -name "plugin.json" -exec \
  sed -i '' "s/$ENGINE_VERSION_PATTERN/$ENGINE_VERSION_REPLACE/" {} +
echo "    engine_version set to ==$VERSION"

echo "==> Building Python package..."
uv build

echo "==> Done. Artifacts in dist/"
