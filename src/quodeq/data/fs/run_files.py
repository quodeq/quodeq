"""Run-directory file mechanics: evaluation counts, status state, evidence
and queue reads, scratch cleanup, fingerprints.

services/_cache, services/_accumulated_data, services/score_run and
services/evaluation_mixin used to do these reads (and the discard-time
unlinks) inline. The mechanics live here; the services keep the guard
decisions (terminal-state sets, staleness rules, what counts as scratch).
Everything is best-effort and never raises — an error degrades to "no
signal" (or a logged skip), not a broken caller.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Sequence
from pathlib import Path

_logger = logging.getLogger(__name__)

_FINGERPRINT_DIRS = ("evaluation", "evidence")
_FINGERPRINT_FILES = ("evaluation.db", "evaluation.db-wal", "events.jsonl")
_EVIDENCE_SUFFIX = "_evidence.jsonl"


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


def list_dimension_evidence(run_dir: Path) -> list[tuple[str, Path, int]] | None:
    """``(dim_id, jsonl_path, size_bytes)`` per ``evidence/<dim>_evidence.jsonl``.

    None (not ``[]``) when the evidence directory is absent, so callers can
    distinguish "run produced nothing at all" from "no evidence files". A
    file that vanishes between glob and stat reports size 0.
    """
    evidence_dir = run_dir / "evidence"
    if not evidence_dir.is_dir():
        return None
    out: list[tuple[str, Path, int]] = []
    for path in evidence_dir.glob(f"*{_EVIDENCE_SUFFIX}"):
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        out.append((path.name[: -len(_EVIDENCE_SUFFIX)], path, size))
    return out


def dimension_queue_file(run_dir: Path, dim_id: str) -> Path:
    """The dim's dispatch-queue path (``evidence/<dim>_queue.json``)."""
    return run_dir / "evidence" / f"{dim_id}_queue.json"


def queue_file_exists(run_dir: Path, dim_id: str) -> bool:
    """True when the dim's dispatch queue exists on disk."""
    return dimension_queue_file(run_dir, dim_id).exists()


def read_queue_files_count(queue_path: Path) -> int:
    """Sum of files across all ``taken`` batches in a dim's queue.json.

    0 when the file is absent, corrupt, or not batch-shaped — this feeds
    coverage counters, never correctness.
    """
    try:
        data = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return 0
    taken = data.get("taken") if isinstance(data, dict) else None
    if not isinstance(taken, list):
        return 0
    total = 0
    for entry in taken:
        files = entry.get("files") if isinstance(entry, dict) else None
        if isinstance(files, list):
            total += len(files)
    return total


def read_dispatched_cache_keys(evidence_dir: Path) -> list[str]:
    """Cache keys from every ``*_dispatch_keys.json`` sidecar in *evidence_dir*.

    Each sidecar maps file path -> cache key for the files THIS run
    dispatched. Unreadable sidecars are logged and skipped; non-dict
    payloads are ignored.
    """
    keys: list[str] = []
    for sidecar in evidence_dir.glob("*_dispatch_keys.json"):
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _logger.warning("Could not read sidecar %s: %s", sidecar, exc)
            continue
        if not isinstance(data, dict):
            continue
        keys.extend(data.values())
    return keys


def remove_matching_files(directory: Path, patterns: Sequence[str]) -> None:
    """Unlink every file in *directory* matching any of *patterns*.

    Already-gone files are fine (another cleaner won the race); other OS
    errors are logged and skipped so one stuck file never blocks the rest.
    """
    for pattern in patterns:
        for victim in directory.glob(pattern):
            try:
                victim.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                _logger.warning("Could not discard %s: %s", victim, exc)


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
