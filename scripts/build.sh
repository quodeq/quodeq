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

echo "==> Building Python package..."
uv build

echo "==> Done. Artifacts in dist/"
