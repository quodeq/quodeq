#!/usr/bin/env bash
# Build the distribution package (sdist + wheel) with pre-built web UI.
#
# Usage:
#   ./tools/build-dist.sh
#
# Prerequisites:
#   - Node.js 20+ and npm 10+
#   - uv (https://docs.astral.sh/uv/)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UI_DIR="${QUODEQ_UI_DIR:-$REPO_ROOT/src/quodeq/ui}"

echo "==> Building web UI..."
cd "$UI_DIR"
npm ci
# vite.config.js writes to ../static (i.e. src/quodeq/static) by default,
# which is exactly where the wheel picks the bundled UI up from.
npm run build
cd "$REPO_ROOT"

echo "==> Building Python package..."
uv build

echo "==> Done. Artifacts in dist/"
ls -lh dist/
