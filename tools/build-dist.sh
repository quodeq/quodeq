#!/usr/bin/env bash
# Build the distribution package (sdist + wheel) with pre-built web UI.
#
# Usage:
#   ./tools/build-dist.sh
#
# Prerequisites:
#   - Node.js 20+ and npm 10+
#   - uv (https://docs.astral.sh/uv/)
#
# Now also syncs engine_version into plugin.json (see tools/build.sh), so the
# dist wheel carries the same plugin-compat pin as a local build.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$(dirname "$0")/_build_common.sh"

build_frontend "$REPO_ROOT"
sync_engine_version "$REPO_ROOT"
build_python "$REPO_ROOT"

echo "==> Done. Artifacts in dist/"
ls -lh "$REPO_ROOT/dist/"
