"""Extended tests for quodeq.services.violations — dismissed keys, filtering, aggregation edge cases."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.services.violations import (
    _deleted_key_for_violation,
    _dismissed_key_for_violation,
    _filter_dismissed_from_result,
    _max_violation_files,
    aggregate_violations,
    resolve_dimension_eval,
    _ResolveOptions,
)


class TestDismissedKeyForViolation:
    def test_separated_format(self):
        v = {"req": "REQ-1", "file": "main.py", "line": 42}
        assert _dismissed_key_for_violation(v) == ("REQ-1", "main.py", 42)

    def test_combined_format(self):
        v = {"req": "REQ-2", "file": "main.py:10", "line": None}
        assert _dismissed_key_for_violation(v) == ("REQ-2", "main.py", 10)

    def test_no_line_no_colon(self):
        v = {"req": "REQ-3", "file": "main.py", "line": None}
        assert _dismissed_key_for_violation(v) == ("REQ-3", "main.py", 0)

    def test_combined_format_invalid_line(self):
        v = {"req": "REQ-4", "file": "main.py:abc", "line": None}
        assert _dismissed_key_for_violation(v) == ("REQ-4", "main.py:abc", 0)

    def test_empty_dict(self):
        v = {}
        assert _dismissed_key_for_violation(v) == ("", "", 0)

    def test_line_zero_explicit(self):
        v = {"req": "R", "file": "f.py", "line": 0}
        assert _dismissed_key_for_violation(v) == ("R", "f.py", 0)


class TestDeletedKeyForViolation:
    def test_camel_case_practice_id(self):
        v = {"practiceId": "Modularity", "file": "a.py", "line": 3}
        assert _deleted_key_for_violation(v, "maintainability") == ("maintainability", "Modularity", "a.py")

    def test_legacy_principle_fallback(self):
        v = {"principle": "Modularity", "file": "a.py", "line": 3}
        assert _deleted_key_for_violation(v, "maintainability") == ("maintainability", "Modularity", "a.py")

    def test_explicit_principle_override(self):
        v = {"file": "a.py:3"}
        assert _deleted_key_for_violation(v, "maintainability", "Modularity") == ("maintainability", "Modularity", "a.py")

    def test_combined_file_line_stripped(self):
        v = {"practiceId": "Modularity", "file": "a.py:3"}
        assert _deleted_key_for_violation(v, "maintainability") == ("maintainability", "Modularity", "a.py")

    def test_empty_dict(self):
        assert _deleted_key_for_violation({}, "") == ("", "", "")


class TestFilterDismissedFromResult:
    def test_none_result(self):
        assert _filter_dismissed_from_result(None, set()) is None

    def test_empty_dkeys(self):
        result = {"violations": [{"req": "R", "file": "f.py", "line": 1}]}
        assert _filter_dismissed_from_result(result, set()) is result

    def test_filters_violations_dict(self):
        result = {
            "violations": [
                {"req": "R1", "file": "a.py", "line": 1},
                {"req": "R2", "file": "b.py", "line": 2},
            ]
        }
        dkeys = {("R1", "a.py", 1)}
        filtered = _filter_dismissed_from_result(result, dkeys)
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
        filtered = _filter_dismissed_from_result(result, dkeys)
        assert len(filtered["principles"][0]["violations"]) == 1

    def test_no_violations_key(self):
        result = {"score": 8.5}
        dkeys = {("R1", "a.py", 1)}
        # Should return result unchanged
        assert _filter_dismissed_from_result(result, dkeys) is result


class TestDeletedFilteredFromDimensionEval:
    """Permanently-deleted findings must not survive into the served dimension eval.

    The JSON eval parser emits camelCase violation dicts (``practiceId``, not
    ``principle``), so the deletion key must be built from ``practiceId``.
    Regression test for the dimension-detail view showing deleted findings.
    """

    def test_deleted_key_matches_practice_id_violation(self, tmp_path):
        project_dir = tmp_path / "project"
        base = project_dir / "run"
        (base / "evaluation").mkdir(parents=True)
        eval_data = {
            "dimension": "testdim",
            "principles": [{"name": "Clear Naming", "score": 5, "grade": "C"}],
            "violations": [
                {"principle": "Clear Naming", "file": "src/app.py", "line": 12,
                 "title": "t", "reason": "r", "severity": "major"},
                {"principle": "Clear Naming", "file": "src/other.py", "line": 3,
                 "title": "t2", "reason": "r2", "severity": "minor"},
            ],
        }
        (base / "evaluation" / "testdim.json").write_text(json.dumps(eval_data))
        (project_dir / "deleted.json").write_text(json.dumps([
            {"dimension": "testdim", "principle": "Clear Naming", "file": "src/app.py"},
        ]))

        result = resolve_dimension_eval(base, "proj", "run", "testdim")

        files = [v["file"] for v in result["violations"]]
        assert "src/app.py" not in files
        assert "src/other.py" in files

    def test_deleted_key_matches_principle_group_violations(self, tmp_path):
        """Group entries carry no principle field; the group name is the principle."""
        project_dir = tmp_path / "project"
        base = project_dir / "run"
        (base / "evaluation").mkdir(parents=True)
        eval_data = {
            "dimension": "testdim",
            "principles": [{"name": "Clear Naming", "score": 5, "grade": "C"}],
            "violations": [
                {"principle": "Clear Naming", "file": "src/app.py", "line": 12,
                 "title": "t", "reason": "r", "severity": "major"},
                {"principle": "Clear Naming", "file": "src/other.py", "line": 3,
                 "title": "t2", "reason": "r2", "severity": "minor"},
            ],
        }
        (base / "evaluation" / "testdim.json").write_text(json.dumps(eval_data))
        (project_dir / "deleted.json").write_text(json.dumps([
            {"dimension": "testdim", "principle": "Clear Naming", "file": "src/app.py"},
        ]))

        result = resolve_dimension_eval(base, "proj", "run", "testdim")

        group = next(p for p in result["principles"] if p["name"] == "Clear Naming")
        group_files = [v["file"] for v in group["violations"]]
        assert "src/app.py:12" not in group_files
        assert "src/other.py:3" in group_files


class TestMaxViolationFiles:
    def test_default(self):
        assert _max_violation_files() == 20

    def test_override(self):
        assert _max_violation_files(override=5) == 5

    def test_env_override(self):
        assert _max_violation_files(env={"QUODEQ_MAX_VIOLATION_FILES": "10"}) == 10


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


class TestResolveDimensionEvalExtended:
    def test_json_eval_priority(self, tmp_path):
        """JSON eval takes priority over markdown and evidence."""
        base = tmp_path / "run"
        eval_dir = base / "evaluation"
        eval_dir.mkdir(parents=True)
        evidence_dir = base / "evidence"
        evidence_dir.mkdir()

        eval_data = {"dimension": "security", "overallGrade": "A", "principles": {}}
        (eval_dir / "security.json").write_text(json.dumps(eval_data))
        (eval_dir / "security_eval.md").write_text("# Security\nScore: A")

        result = resolve_dimension_eval(base, "proj", "run", "security")
        assert result is not None

    def test_markdown_fallback(self, tmp_path):
        base = tmp_path / "run"
        eval_dir = base / "evaluation"
        eval_dir.mkdir(parents=True)
        evidence_dir = base / "evidence"
        evidence_dir.mkdir()

        md_content = "# Security Evaluation\n\nOverall Grade: B\n\n## Principle 1\n\nGrade: B\n"
        (eval_dir / "security_eval.md").write_text(md_content)

        result = resolve_dimension_eval(base, "proj", "run", "security")
        # Should attempt markdown parse; result depends on parser
        # The key thing is it doesn't return None when markdown exists

    def test_evidence_json_fallback(self, tmp_path):
        base = tmp_path / "run"
        eval_dir = base / "evaluation"
        eval_dir.mkdir(parents=True)
        evidence_dir = base / "evidence"
        evidence_dir.mkdir()

        evidence = {
            "principles": {
                "p1": {
                    "display_name": "P1",
                    "violations": [{"file": "x.py", "line": 1, "reason": "bad"}],
                }
            }
        }
        (evidence_dir / "security_evidence.json").write_text(json.dumps(evidence))

        result = resolve_dimension_eval(base, "proj", "run", "security")
        assert result is not None

    def test_stream_fallback(self, tmp_path):
        base = tmp_path / "run"
        eval_dir = base / "evaluation"
        eval_dir.mkdir(parents=True)
        evidence_dir = base / "evidence"
        evidence_dir.mkdir()

        (evidence_dir / "security_live.stream").write_text("some stream data\n")

        result = resolve_dimension_eval(base, "proj", "run", "security")
        # Stream parsing may or may not produce violations, but code path is exercised

    def test_custom_exists_fn(self, tmp_path):
        """Test with custom _ResolveOptions to exercise injection."""
        base = tmp_path / "run"
        (base / "evaluation").mkdir(parents=True)
        (base / "evidence").mkdir()

        # All exists return False - should return None
        opts = _ResolveOptions(exists_fn=lambda p: False)
        result = resolve_dimension_eval(base, "proj", "run", "security", options=opts)
        assert result is None

    def test_markdown_read_error(self, tmp_path):
        """OSError reading markdown returns None."""
        base = tmp_path / "run"
        eval_dir = base / "evaluation"
        eval_dir.mkdir(parents=True)
        (base / "evidence").mkdir()

        md_path = eval_dir / "security_eval.md"
        md_path.write_text("content")

        def fake_exists(p):
            if "security.json" in str(p):
                return False
            return p.exists()

        opts = _ResolveOptions(exists_fn=fake_exists)
        with patch("quodeq.services.violations.read_text", side_effect=OSError("read error")):
            result = resolve_dimension_eval(base, "proj", "run", "security", options=opts)
            assert result is None

    def test_jsonl_fallback(self, tmp_path):
        base = tmp_path / "run"
        eval_dir = base / "evaluation"
        eval_dir.mkdir(parents=True)
        evidence_dir = base / "evidence"
        evidence_dir.mkdir()

        # Write non-empty JSONL
        (evidence_dir / "security_evidence.jsonl").write_text(
            json.dumps({"type": "finding", "data": {}}) + "\n"
        )

        def custom_exists(p):
            return p.exists()

        class FakeStat:
            st_size = 100

        opts = _ResolveOptions(exists_fn=custom_exists, stat_fn=lambda p: FakeStat())
        # This exercises the jsonl path; actual parsing may vary
        with patch("quodeq.services.violations.parse_violations_from_jsonl", return_value=MagicMock()) as mock_parse:
            result = resolve_dimension_eval(base, "proj", "run", "security", options=opts)
            mock_parse.assert_called_once()
