#!/usr/bin/env bash
# Build the full quodeq package (frontend + backend).
# Usage: ./scripts/build.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UI_DIR="${QUODEQ_UI_DIR:-$ROOT/src/quodeq/ui}"

echo "==> Building frontend..."
# vite.config.js writes to ../static (i.e. src/quodeq/static) by default,
# which is exactly where the wheel picks the bundled UI up from.
(cd "$UI_DIR" && npm ci && npm run build)

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
