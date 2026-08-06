"""Tests for quodeq.services.violations — resolution and aggregation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.services.violations import (
    ViolationContext,
    _ResolveOptions,
    aggregate_violations,
    resolve_dimension_eval,
)


class TestViolationContext:
    def test_frozen_dataclass(self):
        ctx = ViolationContext(project="proj", run_id="run-1", dimension="security")
        assert ctx.project == "proj"
        assert ctx.run_id == "run-1"
        assert ctx.dimension == "security"
        with pytest.raises(AttributeError):
            ctx.project = "other"


class TestAggregateViolations:
    def test_empty_dashboard(self):
        result = aggregate_violations({})
        assert result.total == 0
        assert result.critical == 0
        assert result.files == []

    def test_counts_severities(self):
        dashboard = {
            "dimensions": [
                {
                    "totals": {"violationCount": 3, "severity": {"critical": 1, "major": 1, "minor": 1}},
                    "violations": [
                        {"file": "a.py", "severity": "critical"},
                        {"file": "a.py", "severity": "major"},
                        {"file": "b.py", "severity": "minor"},
                    ],
                }
            ]
        }
        result = aggregate_violations(dashboard)
        assert result.total == 3
        assert result.critical == 1
        assert result.major == 1
        assert result.minor == 1
        assert len(result.files) == 2
        top = result.files[0]
        assert top.path == "a.py"
        assert top.count == 2

    def test_violations_without_file_skipped(self):
        dashboard = {
            "dimensions": [
                {
                    "totals": {"violationCount": 1, "severity": {}},
                    "violations": [{"severity": "minor"}],
                }
            ]
        }
        result = aggregate_violations(dashboard)
        assert result.files == []


class TestResolveDimensionEval:
    def test_returns_none_when_no_files(self, tmp_path):
        base = tmp_path / "run-1"
        base.mkdir()
        (base / "evaluation").mkdir()
        (base / "evidence").mkdir()
        result = resolve_dimension_eval(base, "proj", "run-1", "security")
        assert result is None

    def test_resolves_from_evidence_json(self, tmp_path):
        base = tmp_path / "run-1"
        evidence_dir = base / "evidence"
        evidence_dir.mkdir(parents=True)
        eval_dir = base / "evaluation"
        eval_dir.mkdir()
        evidence = {
            "principles": {
                "p1": {
                    "display_name": "Principle 1",
                    "violations": [{"file": "a.py", "line": 10, "reason": "bad"}],
                }
            }
        }
        (evidence_dir / "security_evidence.json").write_text(json.dumps(evidence))
        result = resolve_dimension_eval(base, "proj", "run-1", "security")
        assert result is not None
        assert result.dimension == "security"
        assert len(result.violations) == 1

    def test_resolves_from_eval_json(self, tmp_path):
        base = tmp_path / "run-1"
        eval_dir = base / "evaluation"
        eval_dir.mkdir(parents=True)
        eval_data = {"dimension": "security", "overallGrade": "B", "principles": {}}
        (eval_dir / "security.json").write_text(json.dumps(eval_data))
        result = resolve_dimension_eval(base, "proj", "run-1", "security")
        assert result is not None


class TestAggregateUnknownSeverity:
    def test_unknown_bucket_folds_into_minor_so_chips_sum_to_total(self):
        # build_totals puts missing/invalid severities in an 'unknown'
        # bucket. The summary only exposes critical/major/minor, so unknown
        # findings made critical+major+minor drift below the total.
        from quodeq.services.violations import aggregate_violations

        dashboard = {
            "dimensions": [
                {
                    "totals": {
                        "violationCount": 4,
                        "severity": {"critical": 1, "major": 1, "minor": 1, "unknown": 1},
                    },
                    "violations": [
                        {"file": "a.py", "severity": "critical"},
                        {"file": "a.py", "severity": "major"},
                        {"file": "a.py", "severity": "minor"},
                        {"file": "a.py"},
                    ],
                },
            ],
        }
        summary = aggregate_violations(dashboard)
        assert summary.total == 4
        assert summary.critical + summary.major + summary.minor == summary.total
        assert summary.minor == 2
        f = summary.files[0]
        assert f.critical + f.major + f.minor == f.count


def _compiled_dir_with(tmp_path, *dims):
    """Build a compiled-standards dir containing one empty <dim>.json per dim."""
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir()
    for dim in dims:
        (compiled_dir / f"{dim}.json").write_text("{}")
    return compiled_dir


class TestResolveDimensionEvalRejectsTraversal:
    """dimension is a request path segment (action API "eval" routes). These
    prove a traversal value is rejected before any of resolve_dimension_eval's
    five path-construction sites run, and that the file it reaches for is
    provably real (not merely absent) -- proof the guard, not luck, stopped it.
    """

    def test_dot_dot_segment_cannot_reach_eval_json_outside_run(self, tmp_path):
        base = tmp_path / "run-1"
        (base / "evaluation").mkdir(parents=True)
        (base / "evidence").mkdir()
        secret_dir = tmp_path / "secret"
        secret_dir.mkdir()
        (secret_dir / "leaked.json").write_text(
            json.dumps({"dimension": "leaked", "overallGrade": "A", "principles": {}})
        )
        options = _ResolveOptions(compiled_dir=_compiled_dir_with(tmp_path, "security"))

        result = resolve_dimension_eval(
            base, "proj", "run-1", "../../secret/leaked", options=options,
        )

        assert result is None
        assert (secret_dir / "leaked.json").is_file()  # untouched, genuinely reachable

    def test_dot_dot_segment_cannot_reach_evidence_json_outside_run(self, tmp_path):
        base = tmp_path / "run-1"
        (base / "evaluation").mkdir(parents=True)
        (base / "evidence").mkdir()
        secret_dir = tmp_path / "secret"
        secret_dir.mkdir()
        (secret_dir / "leaked_evidence.json").write_text(
            json.dumps({"principles": {"p1": {"violations": [{"file": "x.py", "reason": "leak"}]}}})
        )
        options = _ResolveOptions(compiled_dir=_compiled_dir_with(tmp_path, "security"))

        result = resolve_dimension_eval(
            base, "proj", "run-1", "../../secret/leaked", options=options,
        )

        assert result is None
        assert (secret_dir / "leaked_evidence.json").is_file()

    def test_absolute_path_dimension_cannot_reach_arbitrary_file(self, tmp_path):
        base = tmp_path / "run-1"
        (base / "evaluation").mkdir(parents=True)
        (base / "evidence").mkdir()
        secret_eval = tmp_path / "secret_eval.json"
        secret_eval.write_text(json.dumps({"dimension": "secret_eval", "overallGrade": "A", "principles": {}}))
        options = _ResolveOptions(compiled_dir=_compiled_dir_with(tmp_path, "security"))

        absolute_dimension = str(tmp_path / "secret_eval")  # ".json" appended by the code
        result = resolve_dimension_eval(
            base, "proj", "run-1", absolute_dimension, options=options,
        )

        assert result is None
        assert secret_eval.is_file()

    def test_null_byte_in_dimension_is_rejected(self, tmp_path):
        base = tmp_path / "run-1"
        (base / "evaluation").mkdir(parents=True)
        (base / "evidence").mkdir()
        options = _ResolveOptions(compiled_dir=_compiled_dir_with(tmp_path, "security"))

        result = resolve_dimension_eval(
            base, "proj", "run-1", "security\0../../../etc/passwd", options=options,
        )

        assert result is None


class TestResolveDimensionEvalValidDimensionsStillResolve:
    def test_builtin_dimension_still_resolves(self, tmp_path):
        base = tmp_path / "run-1"
        eval_dir = base / "evaluation"
        eval_dir.mkdir(parents=True)
        (eval_dir / "security.json").write_text(
            json.dumps({"dimension": "security", "overallGrade": "B", "principles": {}})
        )
        options = _ResolveOptions(compiled_dir=_compiled_dir_with(tmp_path, "security"))

        result = resolve_dimension_eval(base, "proj", "run-1", "security", options=options)

        assert result is not None

    def test_custom_imported_dimension_still_resolves(self, tmp_path):
        base = tmp_path / "run-1"
        eval_dir = base / "evaluation"
        eval_dir.mkdir(parents=True)
        (eval_dir / "my-custom-standard.json").write_text(
            json.dumps({"dimension": "my-custom-standard", "overallGrade": "C", "principles": {}})
        )
        evaluators_dir = tmp_path / "evaluators"
        evaluators_dir.mkdir()
        (evaluators_dir / "my-custom-standard.json").write_text("{}")
        options = _ResolveOptions(
            compiled_dir=_compiled_dir_with(tmp_path, "security"),
            evaluators_dir=evaluators_dir,
        )

        result = resolve_dimension_eval(
            base, "proj", "run-1", "my-custom-standard", options=options,
        )

        assert result is not None
