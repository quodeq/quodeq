"""In-process memo of per-run scoped versions.

A terminal run's key set never changes (see ``score_cache.per_run_versions``),
so its scoped version is a pure function of that key set and the suppression
state hashed by :func:`suppression_state_fingerprint`. Memoizing the version
rather than the keys keeps memory flat: one project's decoded key sets
measured ~180 MB, a version is 64 characters. Keyed by project dir + run id so
isolated test trees never share entries; bounded by a wholesale clear.
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from quodeq.services.wiring import CACHE_WRITER_EPOCH
from quodeq.services.suppression_keys import as_dismissed_keys

if TYPE_CHECKING:
    from quodeq.core.dismissals import DismissedKeys

_MEMO: dict[tuple[str, str], tuple[str, str]] = {}
_LOCK = threading.Lock()
_MEMO_MAX = 16384


def suppression_state_fingerprint(
    params_fingerprint: str,
    dismissed_all: "DismissedKeys | set[tuple]",
    deleted_all: set[tuple],
) -> str:
    """Hash of everything except the run's own keys that feeds run_scoped_version.

    Takes the full dismissed/deleted state rather than the per-run
    intersection (that needs the keys), so any suppression change invalidates
    every memoized version at once and the next call recomputes from the keys.
    """
    payload = json.dumps({
        "epoch": CACHE_WRITER_EPOCH,
        "dismissed": as_dismissed_keys(dismissed_all).version_payload(),
        "deleted": sorted(str(k) for k in deleted_all),
        "params": params_fingerprint,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def memoized_run_version(project_dir: Path, run_id: str, state_fp: str) -> str | None:
    """The run's scoped version computed under *state_fp*, or None when absent."""
    with _LOCK:
        hit = _MEMO.get((str(project_dir), run_id))
    if hit is not None and hit[0] == state_fp:
        return hit[1]
    return None


def remember_run_version(project_dir: Path, run_id: str, state_fp: str, version: str) -> None:
    """Record a terminal run's scoped version for *state_fp*."""
    with _LOCK:
        if len(_MEMO) >= _MEMO_MAX:
            _MEMO.clear()
        _MEMO[(str(project_dir), run_id)] = (state_fp, version)
