"""filter_dismissed_from_result keys deletions per list.

The top-level list keys each violation by its own practiceId; a principle
group keys its violations by the group name, even an empty one.
"""
from __future__ import annotations

from quodeq.services.violations import filter_dismissed_from_result


def test_top_level_deletions_key_on_the_violations_own_practice():
    result = {"violations": [
        {"practiceId": "Modularity", "file": "a.py", "line": 1},
        {"practiceId": "Cohesion", "file": "a.py", "line": 2},
    ]}
    out = filter_dismissed_from_result(result, set(), {("maint", "Modularity", "a.py")}, "maint")
    assert [v["practiceId"] for v in out["violations"]] == ["Cohesion"]


def test_group_deletions_key_on_the_group_name_not_the_violation():
    result = {"principles": [{"name": "Grouped", "violations": [
        {"practiceId": "Modularity", "file": "a.py", "line": 1},
    ]}]}
    out = filter_dismissed_from_result(result, set(), {("maint", "Grouped", "a.py")}, "maint")
    assert out["principles"][0]["violations"] == []


def test_an_unnamed_group_keys_on_the_empty_principle():
    kept = {"practiceId": "Modularity", "file": "a.py", "line": 1}
    result = {"principles": [{"name": "", "violations": [dict(kept)]}]}
    out = filter_dismissed_from_result(result, set(), {("maint", "Modularity", "a.py")}, "maint")
    assert out["principles"][0]["violations"] == [kept]
    result = {"principles": [{"name": "", "violations": [dict(kept)]}]}
    out = filter_dismissed_from_result(result, set(), {("maint", "", "a.py")}, "maint")
    assert out["principles"][0]["violations"] == []
