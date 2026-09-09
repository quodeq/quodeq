#!/usr/bin/env bash
# Shared build steps for tools/build.sh and tools/build-dist.sh.
# Source this file; it defines functions, it does not run anything itself.

build_frontend() {
  local root="$1"
  local ui_dir="${QUODEQ_UI_DIR:-$root/src/quodeq/ui}"
  echo "==> Building frontend..."
  # vite.config.js writes to ../static (i.e. src/quodeq/static) by default,
  # which is exactly where the wheel picks the bundled UI up from.
  (cd "$ui_dir" && npm ci && npm run build)
}

sync_engine_version() {
  local root="$1"
  echo "==> Syncing engine_version in plugin files..."
  local version
  version=$(python3 -c "import tomllib; print(tomllib.load(open('$root/pyproject.toml','rb'))['project']['version'])")
  # Regex pattern matching any pinned engine_version constraint (e.g. "==1.2.3")
  local engine_version_pattern='"engine_version": "==[^"]*"'
  # Replacement string pinning engine_version to the current pyproject.toml version
  local engine_version_replace="\"engine_version\": \"==$version\""
  # evaluators/ is optional; older or trimmed checkouts may not have it
  local search_dirs=()
  local candidate
  for candidate in "$root/evaluators" "$root/tests"; do
    if [ -d "$candidate" ]; then
      search_dirs+=("$candidate")
    fi
  done
  if [ "${#search_dirs[@]}" -gt 0 ]; then
    # Updates the engine_version constraint in every plugin.json to match the current pyproject.toml version
    if [ "$(uname -s)" = "Darwin" ]; then
      find "${search_dirs[@]}" -name "plugin.json" -exec \
        sed -i '' "s/$engine_version_pattern/$engine_version_replace/" {} +
    else
      find "${search_dirs[@]}" -name "plugin.json" -exec \
        sed -i "s/$engine_version_pattern/$engine_version_replace/" {} +
    fi
  fi
  echo "    engine_version set to ==$version"
}

build_python() {
  local root="$1"
  echo "==> Building Python package..."
  (cd "$root" && uv build)
}
