"""Platform dispatch for the PTY backend (mirrors analysis/mcp/router.py idiom)."""
from __future__ import annotations

import sys

if sys.platform == "win32":
    from quodeq.terminal._pty_windows import WindowsPty as PtyBackend, resolve_shell
else:
    from quodeq.terminal._pty_unix import UnixPty as PtyBackend, resolve_shell

__all__ = ["PtyBackend", "resolve_shell"]
