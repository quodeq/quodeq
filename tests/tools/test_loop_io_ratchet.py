"""Loop-IO ratchet: no new file, database, lock or event-log call per loop iteration.

The baseline lists grandfathered sites. It may shrink, never grow.
"""
import check_loop_io


def test_no_new_loop_io_sites():
    new = sorted(set(check_loop_io.collect_violations()) - check_loop_io.load_baseline())
    assert new == [], (
        "New loop-IO site(s): an open/read/write, database connect, lock or "
        "event-log emit inside a loop body in services/, data/ or analysis/. "
        "Hoist the resource out of the loop or batch the writes (emit_many). "
        "If an edit only moved a grandfathered site, hand-edit its line number "
        "in tools/loop_io_baseline.txt instead of regenerating:\n" + "\n".join(new)
    )


def test_baseline_has_no_stale_entries():
    stale = sorted(check_loop_io.load_baseline() - set(check_loop_io.collect_violations()))
    assert stale == [], (
        "Stale entries in tools/loop_io_baseline.txt. If the site was fixed, "
        "remove the entry. If an edit above it shifted its line, hand-edit the "
        "line number; a blind --update-baseline can absorb a genuinely new site "
        "introduced in the same change:\n" + "\n".join(stale)
    )


# Revise DOWNWARD as sites are fixed; NEVER raise without a justification
# reviewed in the PR that raises it.
BASELINE_CEILING = 3  # at introduction: two per-item event emits and one status poll


def test_baseline_only_shrinks():
    count = len(check_loop_io.load_baseline())
    assert count <= BASELINE_CEILING, (
        f"Baseline grew to {count} entries (ceiling {BASELINE_CEILING}). Fix the "
        "new loop IO instead of grandfathering it. If growth is truly justified, "
        "raise BASELINE_CEILING in the same PR and explain why."
    )
