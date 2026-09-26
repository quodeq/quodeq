"""The fault-tolerance baseline is pinned at zero entries.

test_fault_tolerance_ratchet.py already guards that the baseline never
grows and never goes stale. This test guards the other end: the file has
no grandfathered violations left to shrink, so a new broad/bare/empty
except handler (or contextlib.suppress()) has nowhere to hide and fails
CI instead of being added to the list.
"""
import check_fault_tolerance


def test_fault_tolerance_baseline_is_empty():
    baseline = check_fault_tolerance.load_baseline()
    assert baseline == set(), (
        f"tools/fault_tolerance_baseline.txt must stay empty, found "
        f"{sorted(baseline)}. Fix the violation, don't grandfather it."
    )
