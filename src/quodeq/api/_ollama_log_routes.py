"""Ollama log-stream route — SSE tail of ~/.ollama/logs/server.log."""
from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

from flask import Flask

from quodeq.api.provider_log_routes import ProviderLog, register_provider_log_routes
from quodeq.api._sse_log_helpers import sse_tail_generator
from quodeq.shared.constants import PLATFORM_WIN32
from quodeq.shared.env_resolve import resolve_env


def _ollama_log_path(env: Mapping[str, str] | None = None) -> Path | None:
    """Return the platform's Ollama server log path, or None if not present.

    Resolution order:
      1. ``QUODEQ_OLLAMA_LOG`` env var (explicit override for non-default installs)
      2. macOS / Linux: ~/.ollama/logs/server.log
      3. Windows: %LOCALAPPDATA%/Ollama/server.log

    *env* overrides both lookups and defaults to ``os.environ``.
    """
    environ = resolve_env(env)
    override = environ.get("QUODEQ_OLLAMA_LOG")
    if override:
        return Path(override)
    if sys.platform == PLATFORM_WIN32:
        local_app = environ.get("LOCALAPPDATA")
        if not local_app:
            return None
        return Path(local_app) / "Ollama" / "server.log"
    return Path.home() / ".ollama" / "logs" / "server.log"


# Ollama's server.log contains startup banners, model-load traces, and
# per-request entries from the Gin HTTP framework. The request lines (which
# show what quodeq is asking the model for) are the actionable signal; the
# rest is noise for debugging-the-runtime, not debugging-your-evaluation.
#
# Quodeq also polls /api/version every few seconds as a health check —
# those lines say nothing about the evaluation, just confirm the server
# is up. Drop them to keep the stream focused on actual model traffic.
def _is_gin_line(line: str) -> bool:
    if "[GIN]" not in line:
        return False
    if '"/api/version"' in line:
        return False
    return True


def _tail_gin_lines(log_path: Path, offset: int):
    return sse_tail_generator(log_path, offset, line_filter=_is_gin_line)


_OLLAMA_LOG = ProviderLog(
    name="ollama",
    log_path=_ollama_log_path,
    help="Could not locate the Ollama server log. Start the Ollama app or run `ollama serve`.",
    tail=_tail_gin_lines,
)


def register_ollama_log_routes(app: Flask, env: Mapping[str, str] | None = None) -> None:
    """Register the /api/ollama/logs/stream SSE endpoint.

    Auth and *env* capture work as in ``configure_security``.
    """
    register_provider_log_routes(app, _OLLAMA_LOG, env)
