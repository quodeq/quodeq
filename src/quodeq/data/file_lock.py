"""Platform-specific file locking helpers.

Moved inward to ``core/utils/_file_lock.py`` (stdlib-only) so any layer can
use it without reaching into ``data/``; re-exported here for the rest of
the codebase.
"""
from __future__ import annotations

from quodeq.core.utils._file_lock import lock_file, unlock_file  # noqa: F401
