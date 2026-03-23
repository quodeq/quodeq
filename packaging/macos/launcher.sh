#!/bin/bash
set -euo pipefail
# Quodeq macOS launcher — starts the dashboard and opens the browser.

# macOS .app bundles don't inherit the user's shell PATH.
if [ -f "$HOME/.zprofile" ]; then source "$HOME/.zprofile" 2>/dev/null; fi
if [ -f "$HOME/.zshrc" ]; then source "$HOME/.zshrc" 2>/dev/null; fi
if [ -f "$HOME/.bash_profile" ]; then source "$HOME/.bash_profile" 2>/dev/null; fi
# Detect Homebrew prefix — use `brew --prefix` if available, fall back to arch-based defaults.
if command -v brew &>/dev/null; then
    _HOMEBREW_BIN="$(brew --prefix)/bin"
elif [ "$(uname -m)" = "arm64" ]; then
    _HOMEBREW_BIN="/opt/homebrew/bin"
else
    _HOMEBREW_BIN="/usr/local/bin"
fi
export PATH="$PATH:$HOME/.local/bin:$_HOMEBREW_BIN"

# If dashboard is already running, just open the browser.
# Ports 4173-4175 are the Vite preview server default range.
QUODEQ_PORTS="${QUODEQ_PORTS:-4173 4174 4175}"
for PORT in $QUODEQ_PORTS; do
    if curl -s --max-time 3 "http://127.0.0.1:$PORT/api/health" 2>/dev/null | grep -q '"ok"'; then
        open "http://127.0.0.1:$PORT"
        exit 0
    fi
done

# Check Python 3
if ! command -v python3 &>/dev/null; then
    osascript -e 'display dialog "Python 3 is required.\n\nInstall it from:\n  https://python.org\n\nor with Homebrew:\n  brew install python" buttons {"OK"} default button "OK" with icon caution'
    exit 1
fi

# Check Node.js
if ! command -v node &>/dev/null; then
    osascript -e 'display dialog "Node.js is required.\n\nInstall it from:\n  https://nodejs.org\n\nor with Homebrew:\n  brew install node" buttons {"OK"} default button "OK" with icon caution'
    exit 1
fi

# Check Claude Code CLI
if ! command -v claude &>/dev/null; then
    osascript -e 'display dialog "Claude Code CLI is required.\n\nInstall it with:\n  npm i -g @anthropic-ai/claude-code" buttons {"OK"} default button "OK" with icon caution'
    exit 1
fi

# Auto-install quodeq if missing (all prerequisites are present)
QUODEQ=$(command -v quodeq 2>/dev/null)
if [ -z "$QUODEQ" ]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    REQ_FILE="$SCRIPT_DIR/requirements.txt"
    if [ -f "$REQ_FILE" ] && grep -q -- '--hash' "$REQ_FILE"; then
        python3 -m pip install --user --require-hashes -r "$REQ_FILE" 2>&1
    else
        # SECURITY: No pinned hashes available — install from PyPI over TLS.
        # Using --only-binary :all: to reduce supply chain risk by avoiding
        # arbitrary code execution in source distributions (setup.py).
        python3 -m pip install --user --only-binary :all: quodeq 2>&1
    fi
    export PATH="$PATH:$(python3 -m site --user-base)/bin"
    QUODEQ=$(command -v quodeq 2>/dev/null)
    if [ -z "$QUODEQ" ]; then
        osascript -e 'display dialog "Failed to install Quodeq.\n\nTry manually:\n  pip install quodeq" buttons {"OK"} default button "OK" with icon stop'
        exit 1
    fi
fi

# Start the dashboard
exec "$QUODEQ" dashboard
