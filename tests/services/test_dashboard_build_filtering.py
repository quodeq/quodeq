"""Tests for quodeq.services.dashboard — dismissal filtering and history
payload slimming.

Split from test_dashboard.py (further split out of test_dashboard_build.py
to stay under the file-size cap): the run-level dashboard payload must not
resurface dismissed/deleted findings, and previousByDimension /
stalePreviousByDimension / staleDimensions must carry scores + provenance
only, not finding bodies.
"""
from __future__ import annotations

from unittest.mock import patch

from quodeq.core.types import DimensionResult, DimensionSummary
from quodeq.data.fs.report_parser import RunInfo
from quodeq.services.dashboard import build_dashboard


class TestBuildDashboardDismissedFiltering:
    """The run-level dashboard payload must not resurface findings the user
    dismissed or deleted at project level.

    Regression for the 2026-07-04 report: run 03c99d26 showed "1 critical"
    in the history run view for a finding dismissed on 2026-06-20, while the
    dimension detail (which applies the dismissed-keys filter) correctly hid
    it. The run view, the dimension detail, and the accumulated overview must
    all read through the same dismissal semantics.
    """

    def _write_run(self, reports, project="proj", run_id="20260101T000000"):
        """A legacy-style on-disk run with two violations in one dimension."""
        import json as _json

        run_dir = reports / project / run_id
        eval_dir = run_dir / "evaluation"
        eval_dir.mkdir(parents=True)
        violations = [
            {
                "principle": "N/A", "req": "N/A",
                "file": "src/a.py", "line": 73,
                "title": "Arbitrary file read", "severity": "critical",
            },
            {
                "principle": "Modularity", "req": "M-MOD-1",
                "file": "src/b.py", "line": 5,
                "title": "Oversized function", "severity": "major",
            },
        ]
        (eval_dir / "maintainability.json").write_text(_json.dumps({
            "dimension": "maintainability",
            "overallScore": "6.0/10", "overallGrade": "Fair",
            "principles": [], "violations": violations, "compliance": [],
            "totals": {
                "violationCount": 2, "complianceCount": 0,
                "severity": {"critical": 1, "major": 1, "minor": 0},
            },
        }), encoding="utf-8")
        evidence_dir = run_dir / "evidence"
        evidence_dir.mkdir(parents=True)
        (evidence_dir / "manifest.json").write_text('{"language_stats": {}}', encoding="utf-8")
        return run_dir

    def test_dismissed_finding_excluded_and_totals_recounted(self, tmp_path):
        from quodeq.services.dismissed import dismiss_finding

        self._write_run(tmp_path)
        dismiss_finding(tmp_path / "proj", {"req": "N/A", "file": "src/a.py", "line": 73})

        result = build_dashboard(str(tmp_path), "proj", "latest")

        dim = result["dimensions"][0]
        assert [v["file"] for v in dim["violations"]] == ["src/b.py"]
        assert dim["totals"]["violationCount"] == 1
        assert dim["totals"]["severity"]["critical"] == 0
        assert dim["totals"]["severity"]["major"] == 1

    def test_dismissed_count_attached_to_dimension(self, tmp_path):
        from quodeq.services.dismissed import dismiss_finding

        self._write_run(tmp_path)
        dismiss_finding(tmp_path / "proj", {"req": "N/A", "file": "src/a.py", "line": 73})

        result = build_dashboard(str(tmp_path), "proj", "latest")

        assert result["dimensions"][0]["dismissedCount"] == 1

    def test_no_dismissals_leaves_payload_unchanged(self, tmp_path):
        self._write_run(tmp_path)

        result = build_dashboard(str(tmp_path), "proj", "latest")

        dim = result["dimensions"][0]
        assert len(dim["violations"]) == 2
        assert dim["totals"]["violationCount"] == 2
        assert dim["totals"]["severity"]["critical"] == 1
        assert "dismissedCount" not in dim

    def test_deleted_finding_excluded_without_dismissed_count(self, tmp_path):
        from quodeq.services.deleted import delete_finding

        self._write_run(tmp_path)
        delete_finding(tmp_path / "proj", {
            "dimension": "maintainability", "principle": "Modularity", "file": "src/b.py",
        })

        result = build_dashboard(str(tmp_path), "proj", "latest")

        dim = result["dimensions"][0]
        assert [v["file"] for v in dim["violations"]] == ["src/a.py"]
        assert dim["totals"]["violationCount"] == 1
        # Deleted findings are suppressed, not "dismissed": no count is shown.
        assert "dismissedCount" not in dim


class TestHistoryContextSlimming:
    """previousByDimension / stalePreviousByDimension / staleDimensions must
    carry scores + provenance only. No consumer reads finding bodies from
    these keys, and on large projects the bodies dominated the payload
    (~18.6 MB of a 19.9 MB old-run dashboard on a 201-run project).

    Since the trend-cache perf fix these keys are built by the cache-backed
    SCALAR fetcher (the same one the /scores endpoint uses), so the guaranteed
    contract is: bodies (violations/compliance) are empty, and
    dimension/overallScore/overallGrade/provenance survive -- the scores and
    grades the trend context exists to convey. The UI reads none of these three
    keys directly (0 references in the frontend; it reads the scalar fields
    inlined on the selected-run dimensions). For SQL-projected runs the scalar
    reader also drops display-metadata (totals/principles/discipline/
    evidenceDate/sourceFileCount/filesRead) that no consumer reads -- a strict
    payload improvement; the load-bearing scores/grades/provenance stay
    byte-identical (verified against a real 74-run project). For legacy/no-SQL
    runs the reader falls back to full data, so those fields may still appear;
    either way the bodies are dropped and the scalars/provenance match."""

    def _finding(self, i: int, verdict: str = "violation"):
        from quodeq.core.types.finding import Finding
        return Finding(
            practice_id="P1", verdict=verdict, file=f"f{i}.py", line=i,
            reason="a long explanation", snippet="offending()", context="ctx",
            req=f"R{i}",
        )

    def test_history_keys_drop_finding_bodies_but_keep_scores(self, tmp_path):
        from quodeq.core.types.finding import Totals
        runs = [
            RunInfo(run_id="r-new", date_iso="2024-02-01", date_label="2024-02-01", status="complete"),
            RunInfo(run_id="r-old", date_iso="2024-01-01", date_label="2024-01-01", status="complete"),
        ]
        selected_dims = [DimensionResult(
            dimension="security", overall_grade="B", overall_score="7.0/10",
            violations=[self._finding(1)], compliance=[self._finding(2, "compliance")],
        )]
        old_dims = [
            DimensionResult(
                dimension="security", overall_grade="C", overall_score="6.0/10",
                violations=[self._finding(3)],
                totals=Totals(violation_count=1, compliance_count=0),
            ),
            DimensionResult(
                dimension="perf", overall_grade="C", overall_score="5.0/10",
                violations=[self._finding(4)], compliance=[self._finding(5, "compliance")],
                totals=Totals(violation_count=1, compliance_count=1),
            ),
        ]
        summary = DimensionSummary(dimensions_count=1, overall_grade="B", numeric_average=7.0)

        def read_by_run(_root, _project, run_id):
            return selected_dims if run_id == "r-new" else old_dims

        from quodeq.services.dashboard import clear_shared_dimension_cache
        clear_shared_dimension_cache()
        with (
            patch("quodeq.services.dashboard.list_runs", return_value=runs),
            # Selected-run path reads via dashboard.read_run_data; the history
            # trend/previous/stale path reads via the scalar fetcher. In this
            # no-events/no-db tmp project the scalar reader falls back to
            # read_run_data at the runs-module level, so patch there too.
            patch("quodeq.services.dashboard.read_run_data", side_effect=read_by_run),
            patch("quodeq.services._cache.read_run_data", side_effect=read_by_run),
            patch("quodeq.data.fs.report_parser.runs.read_run_data", side_effect=read_by_run),
            patch("quodeq.services.dashboard.summarize_dimensions", return_value=summary),
        ):
            result = build_dashboard(str(tmp_path), "proj-slim-history", "r-new")

        # The selected run's own dimensions keep their full finding bodies.
        assert result["dimensions"][0]["violations"][0]["reason"] == "a long explanation"
        assert result["dimensions"][0]["compliance"]

        # previousByDimension: scores/grades/provenance survive, bodies do not.
        prev = result["previousByDimension"]["security"]
        assert prev["overallGrade"] == "C"
        assert prev["overallScore"] == "6.0/10"
        assert prev["runId"] == "r-old"
        assert prev["violations"] == []
        assert prev["compliance"] == []

        # staleDimensions (perf is missing from the selected run): same rule.
        stale = [d for d in result["staleDimensions"] if d["dimension"] == "perf"]
        assert stale, f"expected perf in staleDimensions, got {result['staleDimensions']}"
        assert stale[0]["overallScore"] == "5.0/10"
        assert stale[0]["stale"] is True
        assert stale[0]["fromRunId"] == "r-old"
        assert stale[0]["violations"] == []
        assert stale[0]["compliance"] == []

        # stalePreviousByDimension follows the same serialization path.
        for dim in result["stalePreviousByDimension"].values():
            assert dim["violations"] == []
            assert dim["compliance"] == []
