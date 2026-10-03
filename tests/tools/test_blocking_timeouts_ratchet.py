"""Blocking-timeout ratchet: every subprocess/HTTP call in src/quodeq has a timeout.

The baseline is pinned empty, and each ALLOWLIST entry must suppress a real
hit on the current tree.
"""
import check_blocking_timeouts


def test_no_new_blocking_timeout_violations():
    baseline = check_blocking_timeouts.load_baseline()
    current = set(check_blocking_timeouts.collect_violations())
    new = current - baseline
    assert not new, (
        f"New blocking-timeout violations: {sorted(new)}. Pass an explicit "
        "timeout= to the call. A site whose wait is already bounded (a reap "
        "right after kill()) goes in ALLOWLIST with a comment, never in the "
        "baseline."
    )


def test_baseline_is_empty():
    baseline = check_blocking_timeouts.load_baseline()
    assert not baseline, (
        f"blocking_timeouts_baseline.txt is pinned empty but lists {sorted(baseline)}. "
        "Fix the call instead of grandfathering it."
    )


def test_every_allowlist_entry_matches_a_real_site(monkeypatch):
    allowlist = check_blocking_timeouts.ALLOWLIST
    monkeypatch.setattr(check_blocking_timeouts, "ALLOWLIST", frozenset())
    unfiltered = set(check_blocking_timeouts.collect_violations())
    stale = allowlist - unfiltered
    assert not stale, (
        f"Stale ALLOWLIST entries in tools/check_blocking_timeouts.py: {sorted(stale)}. "
        "If the line moved, update the entry's line number. If the site is "
        "gone or now carries a timeout, delete the entry: a stale key could "
        "later hide a new violation that lands on the same line."
    )
