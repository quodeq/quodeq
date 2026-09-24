"""Extended tests for quodeq.services.violations — dismissed keys, filtering, aggregation edge cases."""

from __future__ import annotations


from quodeq.services.violations import (
    deleted_key_for_violation,
    filter_dismissed_from_result,
    violation_location,
    _max_violation_files,
    aggregate_violations,
)


class TestViolationLocation:
    def test_separated_format(self):
        v = {"req": "REQ-1", "file": "main.py", "line": 42}
        assert violation_location(v) == ("main.py", 42)

    def test_combined_format(self):
        v = {"req": "REQ-2", "file": "main.py:10", "line": None}
        assert violation_location(v) == ("main.py", 10)

    def test_no_line_no_colon(self):
        v = {"req": "REQ-3", "file": "main.py", "line": None}
        assert violation_location(v) == ("main.py", 0)

    def test_combined_format_invalid_line(self):
        v = {"req": "REQ-4", "file": "main.py:abc", "line": None}
        assert violation_location(v) == ("main.py:abc", 0)

    def test_empty_dict(self):
        v = {}
        assert violation_location(v) == ("", 0)

    def test_line_zero_explicit(self):
        v = {"req": "R", "file": "f.py", "line": 0}
        assert violation_location(v) == ("f.py", 0)


class TestDeletedKeyForViolation:
    def test_camel_case_practice_id(self):
        v = {"practiceId": "Modularity", "file": "a.py", "line": 3}
        assert deleted_key_for_violation(v, "maintainability") == ("maintainability", "Modularity", "a.py")

    def test_legacy_principle_fallback(self):
        v = {"principle": "Modularity", "file": "a.py", "line": 3}
        assert deleted_key_for_violation(v, "maintainability") == ("maintainability", "Modularity", "a.py")

    def test_explicit_principle_override(self):
        v = {"file": "a.py:3"}
        assert deleted_key_for_violation(v, "maintainability", "Modularity") == ("maintainability", "Modularity", "a.py")

    def test_combined_file_line_stripped(self):
        v = {"practiceId": "Modularity", "file": "a.py:3"}
        assert deleted_key_for_violation(v, "maintainability") == ("maintainability", "Modularity", "a.py")

    def test_empty_dict(self):
        assert deleted_key_for_violation({}, "") == ("", "", "")


class TestFilterDismissedFromResult:
    def test_none_result(self):
        assert filter_dismissed_from_result(None, set()) is None

    def test_empty_dkeys(self):
        result = {"violations": [{"req": "R", "file": "f.py", "line": 1}]}
        assert filter_dismissed_from_result(result, set()) is result

    def test_filters_violations_dict(self):
        result = {
            "violations": [
                {"req": "R1", "file": "a.py", "line": 1},
                {"req": "R2", "file": "b.py", "line": 2},
            ]
        }
        dkeys = {("R1", "a.py", 1)}
        filtered = filter_dismissed_from_result(result, dkeys)
        assert len(filtered["violations"]) == 1
        assert filtered["violations"][0]["req"] == "R2"

    def test_filters_principles_violations(self):
        result = {
            "principles": [
                {
                    "name": "P1",
                    "violations": [
                        {"req": "R1", "file": "a.py", "line": 1},
                        {"req": "R2", "file": "b.py", "line": 2},
                    ],
                }
            ]
        }
        dkeys = {("R2", "b.py", 2)}
        filtered = filter_dismissed_from_result(result, dkeys)
        assert len(filtered["principles"][0]["violations"]) == 1

    def test_no_violations_key(self):
        result = {"score": 8.5}
        dkeys = {("R1", "a.py", 1)}
        # Should return result unchanged
        assert filter_dismissed_from_result(result, dkeys) is result


class TestMaxViolationFiles:
    def test_default(self):
        assert _max_violation_files() == 20

    def test_override(self):
        assert _max_violation_files(override=5) == 5

    def test_env_override(self):
        assert _max_violation_files(env={"QUODEQ_MAX_VIOLATION_FILES": "10"}) == 10

    def test_env_override_reaches_aggregate_violations(self, monkeypatch):
        """No ``env=`` injected -- the real process env, through the public
        aggregate_violations() entry point, must cap the top-files list."""
        monkeypatch.setenv("QUODEQ_MAX_VIOLATION_FILES", "1")
        dashboard = {
            "dimensions": [{
                "totals": {"violationCount": 2, "severity": {"major": 2}},
                "violations": [
                    {"file": "a.py", "severity": "major"},
                    {"file": "b.py", "severity": "major"},
                ],
            }],
        }
        result = aggregate_violations(dashboard)
        assert len(result.files) == 1


class TestAggregateViolationsExtended:
    def test_none_dimensions(self):
        result = aggregate_violations({"dimensions": None})
        assert result.total == 0

    def test_multiple_dimensions(self):
        dashboard = {
            "dimensions": [
                {
                    "totals": {"violationCount": 2, "severity": {"critical": 1, "major": 1}},
                    "violations": [
                        {"file": "a.py", "severity": "critical"},
                        {"file": "b.py", "severity": "major"},
                    ],
                },
                {
                    "totals": {"violationCount": 1, "severity": {"minor": 1}},
                    "violations": [
                        {"file": "a.py", "severity": "minor"},
                    ],
                },
            ]
        }
        result = aggregate_violations(dashboard)
        assert result.total == 3
        assert result.critical == 1
        assert result.major == 1
        assert result.minor == 1
        # a.py should be top with 2 violations
        assert result.files[0].path == "a.py"
        assert result.files[0].count == 2

    def test_no_totals_key(self):
        dashboard = {"dimensions": [{"violations": []}]}
        result = aggregate_violations(dashboard)
        assert result.total == 0

    def test_none_violations_list(self):
        dashboard = {"dimensions": [{"totals": {"violationCount": 0, "severity": {}}, "violations": None}]}
        result = aggregate_violations(dashboard)
        assert result.files == []

    def test_unknown_severity_ignored(self):
        dashboard = {
            "dimensions": [
                {
                    "totals": {"violationCount": 1, "severity": {}},
                    "violations": [{"file": "x.py", "severity": "unknown_sev"}],
                }
            ]
        }
        result = aggregate_violations(dashboard)
        assert result.files[0].count == 1
        # unknown severity doesn't increment critical/major/minor on file
        assert result.files[0].critical == 0
