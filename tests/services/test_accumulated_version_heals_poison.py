"""Regression pin: the accumulated-cache algo salt must invalidate pre-#924 rows.

The 2026-07-29 partial-dim-set fix (PR #924) added the staleness guards and
the ``cacheable=`` persist gate, but did NOT bump the algo salt. Any
accumulated row poisoned BEFORE that fix (a mid-run partial dim list rescored
and persisted — see the 2026-07-29 live diagnosis) still hashes to the same
version as a correct recompute, so it is served forever and never self-heals.

Bumping the salt is the healing mechanism: every pre-bump row misses on its
next read and is recomputed under the guards. The literal below is the exact
algo-5 hash for this fixed input; if a refactor ever reverts the salt (or
otherwise reproduces the algo-5 keyspace), this test fails.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services.score_cache import accumulated_cache_version

# accumulated_cache_version() output for the input below under algo 5 —
# the keyspace in which poisoned pre-#924 rows live.
_ALGO5_HASH = "24c0a1de1b6ecbdfd056dfe5f80ba7876d1e9815babb450dec729d47d53bc09b"

_FIXED_INPUT = (
    Path("/tmp/does-not-matter"),
    DEFAULT_PARAMS,
    [("run-a", "complete", "scoped-v-1")],
    None,
)


def test_version_left_the_algo5_keyspace():
    """Rows persisted under algo 5 (incl. poisoned ones) must never hit again."""
    current = accumulated_cache_version(*_FIXED_INPUT)
    assert current != _ALGO5_HASH, (
        "accumulated_cache_version reproduces the algo-5 keyspace: rows "
        "poisoned before PR #924's guards would be served again. Bump the "
        "algo salt in score_cache.py instead of reverting it."
    )


def test_version_is_deterministic():
    """The healing bump must not accidentally make the version non-deterministic."""
    assert accumulated_cache_version(*_FIXED_INPUT) == accumulated_cache_version(*_FIXED_INPUT)
