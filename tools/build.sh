#!/usr/bin/env bash
# Build the full quodeq package (frontend + backend).
# Usage: ./scripts/build.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Standard project layout paths; override via environment if needed.
UI_WEB="${QUODEQ_UI_WEB:-$ROOT/ui/web}"
STATIC_DEST="${QUODEQ_STATIC_DEST:-$ROOT/src/quodeq/static}"

echo "==> Building frontend..."
(cd "$UI_WEB" && npm install && npm run build)

echo "==> Bundling frontend into package..."
rm -rf "$STATIC_DEST"
cp -r "$UI_WEB/dist" "$STATIC_DEST"

echo "==> Syncing engine_version in plugin files..."
VERSION=$(python3 -c "import tomllib; print(tomllib.load(open('$ROOT/pyproject.toml','rb'))['project']['version'])")
# Regex pattern matching any pinned engine_version constraint (e.g. "==1.2.3")
ENGINE_VERSION_PATTERN='"engine_version": "==[^"]*"'
# Replacement string pinning engine_version to the current pyproject.toml version
ENGINE_VERSION_REPLACE="\"engine_version\": \"==$VERSION\""
# Updates the engine_version constraint in every plugin.json to match the current pyproject.toml version
find "$ROOT/evaluators" "$ROOT/tests" -name "plugin.json" -exec \
  sed -i '' "s/$ENGINE_VERSION_PATTERN/$ENGINE_VERSION_REPLACE/" {} +
echo "    engine_version set to ==$VERSION"

echo "==> Building Python package..."
uv build

echo "==> Done. Artifacts in dist/"
