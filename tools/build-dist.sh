#!/usr/bin/env bash
# Build the distribution package (sdist + wheel) with pre-built web UI.
#
# Usage:
#   ./scripts/build-dist.sh
#
# Prerequisites:
#   - Node.js 18+ and npm 8+
#   - uv (https://docs.astral.sh/uv/)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Standard project layout paths; override via environment if needed.
STATIC_DIR="${QUODEQ_STATIC_DIR:-$REPO_ROOT/src/quodeq/static}"
WEB_DIR="${QUODEQ_WEB_DIR:-$REPO_ROOT/ui/web}"

echo "==> Building web UI..."
cd "$WEB_DIR"
npm install
npm run build
cd "$REPO_ROOT"

echo "==> Copying dist to bundled static directory..."
rm -rf "$STATIC_DIR"
cp -r "$WEB_DIR/dist" "$STATIC_DIR"

echo "==> Building Python package..."
uv build

echo "==> Done. Artifacts in dist/"
ls -lh dist/
