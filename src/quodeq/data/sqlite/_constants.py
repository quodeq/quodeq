"""Constants shared across quodeq.data.sqlite (and its sibling data.cache_store)."""
from __future__ import annotations

# PRAGMA busy_timeout for every WAL-mode sqlite connection this package opens
# (assistant, evaluation, precedent-vectors and score-cache DBs) plus the
# content-index sidecar in quodeq.data.cache_store. Public: re-exported by
# this package's __init__ for that cross-package use.
SQLITE_BUSY_TIMEOUT_MS = 5000
