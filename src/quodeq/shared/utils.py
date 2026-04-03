"""Shared utilities -- intentional convenience facade for the quodeq package.

**Architectural rationale:**  This module provides a single, stable public
import surface so that callers can write
``from quodeq.shared.utils import ...`` without tracking which internal
submodule each helper lives in.  The trade-off (broader module surface) is
a deliberate design choice that keeps imports simple and predictable across
a fast-moving CLI codebase.

Categories of re-exported utilities
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **I/O helpers** -- ``read_text``, ``write_text``, ``open_text``, ``read_json``
   (from ``_io.py``)
2. **Security helpers** -- ``SENSITIVE_PATTERNS``, ``sanitize_sensitive``
   (from ``_security.py``)
3. **Config loading** -- ``Config`` dataclass, lazy singleton via ``_get_config()``
   (from ``_config.py``)
4. **Platform detection** -- ``IS_WIN32``
5. **Repository URL helpers** -- ``is_repo_url``, ``project_name_from_repo``
   (from ``_repo.py``)
6. **Environment accessors** -- ``get_ai_provider``, ``get_dashboard_port``,
   ``get_evaluations_dir``, ``get_anthropic_api_key``, etc.
   (from ``_env.py``)
7. **Diff display** -- ``show_diff`` (from ``_diff.py``)
"""
from __future__ import annotations

import sys

# ---------------------------------------------------------------------------
# Re-exports — I/O and security helpers
# ---------------------------------------------------------------------------

from quodeq.shared._io import TEXT_ENCODING, read_text, write_text, open_text, read_json  # noqa: F401
from quodeq.shared._security import SENSITIVE_PATTERNS, sanitize_sensitive  # noqa: F401

# ---------------------------------------------------------------------------
# Re-exports — Config loading
# ---------------------------------------------------------------------------

from quodeq.shared._config import Config, ACTION_API_MODULE, _get_config  # noqa: F401

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

IS_WIN32: bool = sys.platform == "win32"
"""True when the current platform is Windows (win32)."""

# ---------------------------------------------------------------------------
# Re-exports — Repository URL helpers
# ---------------------------------------------------------------------------

from quodeq.shared._repo import is_repo_url, project_name_from_repo  # noqa: F401

# ---------------------------------------------------------------------------
# Re-exports — Environment accessors
# ---------------------------------------------------------------------------

from quodeq.shared._env import (  # noqa: F401
    get_ai_provider, get_ai_cmd, get_ai_model, _env_int,
    get_action_api_port, get_action_api_host,
    get_dashboard_port, get_static_dist, get_evaluations_dir,
    get_anthropic_api_key, get_asvs_url,
    get_github_search_url, get_github_raw_base_url, get_findings_file,
)

# ---------------------------------------------------------------------------
# Re-exports — Diff display
# ---------------------------------------------------------------------------

from quodeq.shared._diff import show_diff  # noqa: F401


def __getattr__(name: str) -> str:
    """Lazy accessor for config-derived constants (ANTHROPIC_API_URL, etc.)."""
    from quodeq.shared.config_loader import __getattr__ as _cl_getattr
    return _cl_getattr(name)


__all__ = [
    # I/O helpers (re-exported from _io.py)
    "TEXT_ENCODING", "read_text", "write_text", "open_text", "read_json",
    # Security helpers (re-exported from _security.py)
    "SENSITIVE_PATTERNS", "sanitize_sensitive",
    # Config
    "Config", "ACTION_API_MODULE",
    # Platform
    "IS_WIN32",
    # Repo URL helpers
    "is_repo_url", "project_name_from_repo",
    # Environment accessors
    "get_ai_provider", "get_ai_cmd", "get_ai_model", "_env_int",
    "get_action_api_port", "get_action_api_host",
    "get_dashboard_port", "get_static_dist", "get_evaluations_dir",
    "get_anthropic_api_key", "get_asvs_url",
    "get_github_search_url", "get_github_raw_base_url", "get_findings_file",
    # Diff
    "show_diff",
]
