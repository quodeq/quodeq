"""Parameter-count gate: fail the build on NEW functions with more than 5 parameters."""
from __future__ import annotations

import check_params


def test_no_new_param_violations():
    baseline = check_params.load_baseline()
    new = sorted(set(check_params.collect_violations()) - baseline)
    assert new == [], (
        "New function(s) with more than 5 parameters. Pass an options object "
        "(frozen dataclass) or split the function; only with justification run "
        "`python tools/check_params.py --update-baseline`:\n" + "\n".join(new)
    )


# Revise DOWNWARD as maintainability workstreams burn entries; NEVER raise
# without a justification reviewed in the PR that raises it.
BASELINE_CEILING = 74  # set to the count --update-baseline printed in Task 1 step 6


def test_baseline_only_shrinks():
    """The grandfathered list is a burn-down list, not a dumping ground."""
    count = len(check_params.load_baseline())
    assert count <= BASELINE_CEILING, (
        f"Baseline grew to {count} entries (ceiling {BASELINE_CEILING}). "
        "Fix the new function instead of grandfathering it. If growth is truly "
        "justified, raise BASELINE_CEILING in the same PR and explain why."
    )


def test_baseline_has_no_stale_entries():
    """Fixing a violation must shrink the baseline, keeping it honest."""
    current = set(check_params.collect_violations())
    stale = sorted(check_params.load_baseline() - current)
    assert stale == [], (
        "Baseline lists violations that no longer exist; regenerate with "
        "`python tools/check_params.py --update-baseline`:\n" + "\n".join(stale)
    )


def test_violation_keys_have_no_collisions():
    """relpath:qualname collides for same-named siblings (@overload stacks,
    property getter/setter, platform-branch defs). If this fails, rename
    the colliding over-limit function, or extend the key scheme to
    disambiguate."""
    keys = [check_params.violation_key(v) for v in check_params._scan()]
    assert len(keys) == len(set(keys))
