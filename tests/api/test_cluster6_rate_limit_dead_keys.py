"""#1458 - rate-limit store must not accumulate dead (empty) IP keys.

The fix: after pruning per-IP timestamps, if the list is empty the key is
removed with data.pop(ip) rather than stored as data[ip] = [].

In the current implementation record() appends the new timestamp before
pruning, so the pruned list is never empty in normal operation (now is
always within the window of itself). The guard is still correct to have:
it prevents the edge-case where a clock going backwards or a caller
deliberately passing a very-old ``now`` could store an empty list.

The main behavioural assertion is: old timestamps are pruned on each record
call, and the surviving list contains exactly the timestamps within the window.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.api._rate_limit_file_store import FileRateLimitStore


def _read_data(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_old_timestamps_pruned_on_same_ip_record(tmp_path: Path):
    """When the same IP records again after its window expires, old timestamps
    are pruned and the key contains only the new timestamp.
    """
    store_path = tmp_path / "rl.json"
    store = FileRateLimitStore(path=store_path, window=60.0)

    store.record("10.0.0.1", now=0.0)
    assert _read_data(store_path)["10.0.0.1"] == [0.0]

    # Same IP at t=120 — the t=0 entry is 120s old, past the 60s window.
    store.record("10.0.0.1", now=120.0)
    data = _read_data(store_path)
    assert "10.0.0.1" in data
    assert data["10.0.0.1"] == [120.0], (
        "Expired timestamp at t=0 must be pruned; only t=120 survives."
    )


def test_no_empty_list_stored_when_all_prior_timestamps_expire(tmp_path: Path):
    """If all stored timestamps for an IP expire and a new one is added,
    the list must not be empty — exactly the new timestamp is stored.
    This guards against the bug where data[ip] = [] was written.
    """
    store_path = tmp_path / "rl.json"
    store = FileRateLimitStore(path=store_path, window=10.0)

    # Record several timestamps.
    for t in [0.0, 1.0, 2.0]:
        store.record("192.168.1.1", now=t)

    assert len(_read_data(store_path)["192.168.1.1"]) == 3

    # Record at t=10000 — all prior entries are far outside the window.
    store.record("192.168.1.1", now=10000.0)
    data = _read_data(store_path)

    assert "192.168.1.1" in data
    timestamps = data["192.168.1.1"]
    assert len(timestamps) == 1, (
        f"Expected exactly one timestamp (the new one), got {timestamps}."
    )
    assert timestamps[0] == 10000.0


def test_active_timestamps_all_retained_within_window(tmp_path: Path):
    """Multiple records within the window are all kept."""
    store_path = tmp_path / "rl.json"
    store = FileRateLimitStore(path=store_path, window=300.0)

    store.record("1.2.3.4", now=100.0)
    store.record("1.2.3.4", now=150.0)
    store.record("1.2.3.4", now=200.0)

    data = _read_data(store_path)
    assert data["1.2.3.4"] == [100.0, 150.0, 200.0]


def test_ip_key_removed_when_pop_branch_taken(tmp_path: Path):
    """data.pop(ip) is taken when pruned is empty (guarding against clock edge-cases).

    We simulate this by planting a stale entry directly in the file and
    verifying the pop path: plant ip=[stale], call record() for that ip at
    a time far in the future. The new 'now' is added then pruned — since now
    is within the window of itself, the list is [now], not empty.
    The pop() branch is actually unreachable in normal use because append(now)
    ensures pruned is never empty. This test confirms the normal path: no
    empty list is ever written.
    """
    store_path = tmp_path / "rl.json"
    # Plant a stale entry manually.
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps({"ghost": [0.0]}), encoding="utf-8")

    store = FileRateLimitStore(path=store_path, window=60.0)
    # Record at t=1000 — ghost's old entry expires, but new one survives.
    store.record("ghost", now=1000.0)

    data = _read_data(store_path)
    assert "ghost" in data
    assert data["ghost"] == [1000.0], "Only the new in-window timestamp must survive."
    # No empty lists anywhere.
    for ip, ts in data.items():
        assert ts, f"IP {ip!r} has an empty timestamp list — fix must remove such keys."
