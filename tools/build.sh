#!/usr/bin/env bash
# Build the full quodeq package (frontend + backend).
# Usage: ./scripts/build.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$(dirname "$0")/_build_common.sh"

build_frontend "$ROOT"
sync_engine_version "$ROOT"
build_python "$ROOT"

echo "==> Done. Artifacts in dist/"
