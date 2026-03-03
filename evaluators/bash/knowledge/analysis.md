# Bash / Shell Codebase Analysis Guidance

## Where to look first

### Security hotspots
- **Unquoted variables** — `$VAR` without quotes enables word splitting and injection.
- **Hardcoded secrets** — `API_KEY='...'` in scripts.
- **eval usage** — `eval "$cmd"` with user-controlled input.

### Maintainability signals
- **Script length** — scripts over 200 LOC should be split into functions or separate scripts.
- **Missing functions** — long procedural scripts without function decomposition.
- **No shellcheck compliance** — common pitfalls detectable by shellcheck.

### Reliability signals
- **Missing `set -euo pipefail`** — scripts without error flags silently continue on failure.
- **Unchecked return codes** — commands without `|| exit 1` or `set -e`.
- **Missing cleanup traps** — no `trap cleanup EXIT` for temp file cleanup.

### Performance signals
- **Subshell overuse** — `$(cat file)` instead of `< file` redirection.
- **Unnecessary external commands** — using `grep | awk | sed` chains when one tool suffices.
