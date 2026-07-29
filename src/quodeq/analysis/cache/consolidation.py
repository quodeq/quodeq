"""Consolidation state — flip a completed run's cache entries.

A cache entry is written ``consolidated=False``: the findings it holds have
not reached any completed run's report yet. Once a run reaches ``done``,
everything it dispatched and every unconsolidated entry it replayed IS in a
completed run's report, so those entries flip to ``consolidated=True`` and
later runs replay their findings as carried forward.

Runs that end any other way, cancelled with "keep findings", failed, or
killed, simply never call this. That inversion is the design: not running is
the only thing a dead process can reliably do.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from quodeq.analysis.cache.backend import CacheBackend

_logger = logging.getLogger(__name__)

# Both sidecars a run leaves behind, each mapping file path -> cache key.
# dispatch_keys holds what the run produced; replayed_unconsolidated_keys
# holds entries from an earlier unfinished run that this run replayed and
# has now put in its own report.
_SIDECAR_PATTERNS = (
    "*_dispatch_keys.json",
    "*_replayed_unconsolidated_keys.json",
)


def _run_reached_done(run_dir: Path) -> bool:
    """True only when the run's recorded state is ``done``.

    Reading the recorded state rather than trusting an exit code keeps this
    on the same source of truth the Overview uses, so the two cannot drift.
    A missing or corrupt status is not done.
    """
    try:
        data = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and data.get("state") == "done"


def _collect_keys(evidence_dir: Path) -> set[str]:
    """Every cache key this run touched, from both sidecar families.

    An unreadable sidecar is logged and skipped so one bad file cannot cost
    the run its whole consolidation pass.
    """
    keys: set[str] = set()
    for pattern in _SIDECAR_PATTERNS:
        for sidecar in evidence_dir.glob(pattern):
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                _logger.warning("Could not read sidecar %s: %s", sidecar, exc)
                continue
            if isinstance(data, dict):
                keys.update(str(value) for value in data.values())
    return keys


def mark_run_consolidated(
    run_dir: Path, cache: CacheBackend | None = None,
) -> None:
    """Flip this run's cache entries to consolidated, if it reached done.

    Fail-soft in every direction. A non-done run, a missing run dir, an
    unreadable sidecar, a key with no entry, or a backend that raises all
    leave the cache as it was. Callers invoke this OUTSIDE the run lifecycle
    so a failure here can never flip a done run to failed.

    Self-healing: entries missed by a partial pass are replayed as
    unconsolidated hits by the next run, land in that run's replayed-keys
    sidecar, and flip when it completes. There is no repair path to run and
    no stuck state to recover from.
    """
    try:
        if not _run_reached_done(run_dir):
            return
        evidence_dir = run_dir / "evidence"
        if not evidence_dir.is_dir():
            return
        keys = _collect_keys(evidence_dir)
        if not keys:
            return
        if cache is None:
            from quodeq.analysis.cache.local import LocalFileBackend  # noqa: PLC0415
            cache = LocalFileBackend()
        flipped = 0
        for key in sorted(keys):
            try:
                entry = cache.get(key)
                if entry is None or entry.consolidated:
                    continue
                entry.consolidated = True
                cache.put(key, entry)
                flipped += 1
            except Exception as exc:  # noqa: BLE001 — one bad entry must not stop the rest
                _logger.warning("Could not consolidate cache entry %s: %s", key, exc)
        _logger.info(
            "cache: consolidated %d entries for run %s", flipped, run_dir.name,
        )
    except Exception:  # noqa: BLE001 — post-scan side effect, never propagates
        _logger.warning(
            "Consolidation pass failed for %s (evaluation results are safe)",
            run_dir, exc_info=True,
        )
