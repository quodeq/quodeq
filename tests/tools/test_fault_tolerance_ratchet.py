"""Fault-tolerance ratchet: no new bare/empty/overly-broad except handlers.

Baseline lists grandfathered violations. It may shrink, never grow.
"""
import check_fault_tolerance


def test_no_new_fault_tolerance_violations():
    baseline = check_fault_tolerance.load_baseline()
    current = set(check_fault_tolerance.collect_violations())
    new = current - baseline
    assert not new, (
        f"New fault-tolerance violations (fix the except handler, don't "
        f"grandfather it): {sorted(new)}"
    )


def test_baseline_has_no_stale_entries():
    baseline = check_fault_tolerance.load_baseline()
    current = set(check_fault_tolerance.collect_violations())
    stale = baseline - current
    assert not stale, (
        f"Stale entries in fault_tolerance_baseline.txt: {sorted(stale)}. "
        "If the violation was actually fixed, remove the entry. If the file "
        "just shifted lines (an edit elsewhere in the file moved this "
        "violation to a new line number), hand-edit the entry's line number "
        "instead of regenerating the whole baseline -- a blind "
        "--update-baseline can silently absorb a genuinely new violation "
        "introduced in the same change."
    )


# Revise DOWNWARD as fault-tolerance findings burn entries; NEVER raise
# without a justification reviewed in the PR that raises it.
# 221 = 219 (final review baseline) + 2 `suppress` entries grandfathered when
# the scanner was extended to see contextlib.suppress() (final review item D,
# fault-tolerance cycle 1 fix wave): dashboard/_webview_token.py:85 and
# data/fs/run_artifacts.py:60, both pre-existing, previously invisible.
BASELINE_CEILING = 221  # set to the count --update-baseline printed in Step 1


def test_baseline_only_shrinks():
    count = len(check_fault_tolerance.load_baseline())
    assert count <= BASELINE_CEILING, (
        f"Baseline grew to {count} entries (ceiling {BASELINE_CEILING}). "
        "Fix the new except handler instead of grandfathering it. If "
        "growth is truly justified, raise BASELINE_CEILING in the same PR "
        "and explain why."
    )
