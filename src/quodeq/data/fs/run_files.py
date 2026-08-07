"""Run-directory read mechanics: evaluation counts, status state, fingerprints.

services/_cache and services/_accumulated_data used to do these reads
inline. The mechanics live here; the services keep the guard decisions
(terminal-state sets, staleness rules). Every read is best-effort and
never raises — these functions sit under cache guards where an error must
degrade to "no signal", not break the caller.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

_FINGERPRINT_DIRS = ("evaluation", "evidence")
_FINGERPRINT_FILES = ("evaluation.db", "evaluation.db-wal", "events.jsonl")


def count_eval_files(run_dir: Path) -> int | None:
    """Number of ``evaluation/*.json`` files, or None when the dir is absent.

    None vs 0 matters: callers anchored on the directory existing (unit
    tests that pre-seed caches) must treat "no directory" as "no signal".
    """
    eval_dir = run_dir / "evaluation"
    if not eval_dir.is_dir():
        return None
    try:
        return sum(1 for p in eval_dir.iterdir() if p.suffix == ".json")
    except OSError:
        return None


def read_run_state(run_dir: Path) -> str | None:
    """The ``state`` string from ``status.json``, or None when absent,
    corrupt, non-dict, or non-string.

    Unlike ``run_status_store.read_status`` this never raises (no schema
    check): it feeds cache guards, where any read problem must degrade to
    "no signal".
    """
    path = run_dir / "status.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    state = data.get("state") if isinstance(data, dict) else None
    return state if isinstance(state, str) else None


def run_fingerprint(run_dir: Path) -> str:
    """Cheap content fingerprint for the inputs ``read_run_data`` reads.

    Stat-based rather than hash-based: the point is to be far cheaper than
    the read it guards, while still changing whenever a run's data is
    rewritten in place (see :data:`_FINGERPRINT_FILES`).
    """
    parts: list[str] = []
    for sub in _FINGERPRINT_DIRS:
        try:
            entries = sorted((run_dir / sub).iterdir())
        except OSError:
            continue
        for path in entries:
            try:
                stat = path.stat()
            except OSError:
                continue
            parts.append(f"{sub}/{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
    for name in _FINGERPRINT_FILES:
        try:
            stat = (run_dir / name).stat()
        except OSError:
            continue
        parts.append(f"{name}:{stat.st_mtime_ns}:{stat.st_size}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
