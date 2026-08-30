"""Read-through cache of rescored per-run dimension scalars.

Keyed by a content-hash version of the project's dismissals/deletions + grade
params, so any change auto-invalidates. Disposable/best-effort: a corrupt or
older-schema db is rebuilt, and any cache error falls through to recompute.

This module owns the version hashes (the cache's invalidation contract) and is
the facade every caller imports. The mechanics live in three submodules:
``_score_cache_db`` (connection/schema), ``_score_cache_store`` (per-table
reads/writes) and ``_score_cache_fetch`` (read-through wrappers).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from quodeq.core.scoring.params import ScoringParams
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services._score_cache_epoch import CACHE_WRITER_EPOCH as _CACHE_WRITER_EPOCH
from quodeq.services.ports import load_suppression_rules

# ---------------------------------------------------------------------------
# Decomposed submodules. Every moved name is re-exported here so external
# callers and test patch targets keep working against this module.
# ---------------------------------------------------------------------------
from quodeq.services._score_cache_db import (  # noqa: F401 — facade re-export
    open_score_cache,
    score_cache_path_override,
)
from quodeq.services._score_cache_store import (  # noqa: F401 — facade re-export
    load_run_keys,
    read_cached_accumulated,
    read_cached_project_summary,
    read_cached_rows,
    store_run_keys,
    write_cached_accumulated,
    write_cached_project_summary,
    write_cached_rows,
)
from quodeq.services._score_cache_fetch import (  # noqa: F401 — facade re-export
    cached_accumulated,
    cached_project_summary,
    make_cache_backed_fetcher,
)
from quodeq.shared._env import get_score_cache_path  # noqa: F401 — facade re-export


def _params_fingerprint(params: ScoringParams) -> str:
    """Deterministic serialization of the grade-formula params (sorted maps)."""
    return json.dumps({
        "severity_weight": dict(sorted(params.severity_weight.items())),
        "base_k": params.base_k,
        "lift_compress": params.lift_compress,
        "ceil_scale": params.ceil_scale,
        "floor_minor": params.floor_minor,
        "floor_major": params.floor_major,
        "grade_thresholds": [list(t) for t in params.grade_thresholds],
        "dimension_weights_enabled": params.dimension_weights_enabled,
        "dimension_weights": dict(sorted(params.dimension_weights.items())),
    }, sort_keys=True)


def score_cache_version(project_dir: Path, params: ScoringParams) -> str:
    """Content-hash of the project's suppression state + grade params.

    Any change to any of these produces a new version, auto-invalidating cached
    rows without a write-path hook. Pattern rules are part of the state for the
    same reason the exact keys are: adding one hides findings, so a cached row
    computed before it must not survive.
    """
    payload = json.dumps({
        "epoch": _CACHE_WRITER_EPOCH,
        "dismissed": sorted(str(k) for k in dismissed_keys(project_dir)),
        "deleted": sorted(str(k) for k in deleted_keys(project_dir)),
        "rules": [
            [r.req, r.file, r.reason] for r in load_suppression_rules(project_dir)
        ],
        "params": _params_fingerprint(params),
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_scoped_version(
    params: ScoringParams,
    run_dismiss_keys: set[tuple],
    run_class_keys: set[tuple],
    dismissed_all: set[tuple],
    deleted_all: set[tuple],
) -> str:
    """Version hash for a single run: params + only the suppressions that touch it.

    A run's rescored score depends solely on dismissals whose (req,file,line) is
    in *run_dismiss_keys* and deletions whose (dim,principle,file) is in
    *run_class_keys*, so intersecting keeps unaffected runs' versions stable.
    """
    payload = json.dumps({
        "epoch": _CACHE_WRITER_EPOCH,
        "dismissed": sorted(str(k) for k in (dismissed_all & run_dismiss_keys)),
        "deleted": sorted(str(k) for k in (deleted_all & run_class_keys)),
        "params": _params_fingerprint(params),
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def accumulated_cache_version(
    project_dir: Path, params: ScoringParams,
    run_versions: list[tuple], as_of: str | None,
    visible_dims: tuple[str, ...] | None = None,
) -> str:
    """Version for the accumulated cache: params + the per-run fingerprints +
    *as_of*. Composing per-run fingerprints means a dismiss/delete on one run
    invalidates the accumulated payload only when that run's contribution
    actually changed (its scoped version changed).

    Each fingerprint tuple carries the run's *status* alongside its scoped
    version (see :func:`per_run_versions`) so a status transition (e.g.
    ``in_progress -> complete``, ``complete -> cancelled``) changes the hash and
    invalidates the cache. The scoped version is status-independent — it hashes
    params + intersecting suppressions — so without status folded in, a run
    completing mid-poll would recompute the same version and serve a stale
    payload that omitted the just-finished (now eligible) run.

    *visible_dims* is folded in only by payloads that are COMPUTED over the
    visible-standards selection (the project-card summary): toggling a
    standard must invalidate them. Payloads that return every dimension and
    leave filtering to the client (the accumulated Overview) pass None, so
    their hashes are unaffected by visibility edits.
    """
    payload = json.dumps({
        # Bump when the accumulated / project-card computation changes, so
        # existing cache entries recompute on deploy instead of serving a stale
        # value until the next scan/dismiss/delete. v4: fold each run's status
        # back into its fingerprint so a status flip re-invalidates (v3 composed
        # only status-independent scoped versions and lost that guard). v5:
        # dimensions are no longer scoped to the last-5-runs configured
        # standard; payloads written with scoping omit dimensions whose last
        # valid run is older and must rebuild. v6: heal rows poisoned before
        # PR #924's partial-dim guards — a mid-run partial rescore persisted
        # under algo 5 hashes identically to a correct recompute, so without
        # this bump it is served forever (tests/services/
        # test_accumulated_version_heals_poison.py pins the keyspace exit).
        "algo": 6,
        "params": _params_fingerprint(params),
        "runs": sorted(list(t) for t in run_versions),
        "as_of": as_of or "",
        **({} if visible_dims is None else {"visible": sorted(visible_dims)}),
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def per_run_versions(
    project_dir: Path, project: str, params: ScoringParams,
    runs: list[tuple[str, str]],
) -> list[tuple[str, str, str]]:
    """``(run_id, status, scoped_version)`` per run, from persisted/lazy run_keys.

    *runs* is a list of ``(run_id, status)`` pairs. The returned ``status`` is
    folded into the accumulated version so a status transition invalidates the
    cache (see :func:`accumulated_cache_version`).

    Only TERMINAL runs persist their key sets: an in-progress run's findings
    table is still being written as dimensions finish, so its key set is partial.
    Persisting that partial snapshot would freeze it (``load_run_keys`` short-
    circuits any re-read), so a suppression targeting a key that appears only
    after the run is first observed mid-scan would not intersect the frozen set
    and would silently under-invalidate. Non-terminal runs therefore compute
    their scoped version from a fresh ``read_run_key_sets`` each call and never
    write it back, mirroring ``_trend_fetcher.version_for``.
    """
    from quodeq.services.deleted import deleted_keys  # noqa: PLC0415
    from quodeq.services.dismissed import dismissed_keys  # noqa: PLC0415
    from quodeq.services.run_keys import read_run_key_sets  # noqa: PLC0415
    dismissed, deleted = dismissed_keys(project_dir), deleted_keys(project_dir)
    try:
        with open_score_cache() as conn:
            cached = load_run_keys(conn, project)
    except sqlite3.Error:
        cached = {}
    out: list[tuple[str, str, str]] = []
    for rid, status in runs:
        terminal = status == "complete"
        keys = cached.get(rid) if terminal else None
        if keys is None:
            keys = read_run_key_sets(project_dir / rid)
            if terminal:
                try:
                    with open_score_cache() as conn:
                        store_run_keys(conn, project, rid, keys[0], keys[1])
                except sqlite3.Error:
                    pass
        out.append(
            (rid, status, run_scoped_version(params, keys[0], keys[1], dismissed, deleted)))
    return out
