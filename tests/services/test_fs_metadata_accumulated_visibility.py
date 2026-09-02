"""Tests for _fs_metadata.py — _read_accumulated_summary and standards
visibility selection.

Split from test_fs_metadata.py (further split out of
test_fs_metadata_accumulated.py to stay under the file-size cap): dims
absent from the latest run's config, hidden-standards exclusion, the
default ISO selection, cache invalidation on visibility change, and the
SQL-grade/loaded-params overlay all part of the same TestReadAccumulatedSummary
suite in the original file.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from quodeq.services._fs_metadata import _read_accumulated_summary


class TestReadAccumulatedSummary:
    @patch("quodeq.services._fs_metadata.summarize_dimensions")
    @patch("quodeq.services._fs_metadata.read_run_data")
    def test_card_summary_keeps_dims_not_in_latest_config(
        self, mock_read, mock_summarize, tmp_path, monkeypatch,
    ):
        """Dims absent from the latest run's config are KEPT (show all,
        count all) so the card grade matches the accumulated overview."""
        from quodeq.core.types import DimensionResult
        from quodeq.data.fs.report_parser.runs import RunInfo

        # Bypass the persisted project-summary cache so we observe the fresh
        # computation (the cache is keyed by project name, not reports_root).
        monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
        reports_root = tmp_path / "evaluations"
        project = "proj"
        latest_dir = reports_root / project / "run-new"
        latest_dir.mkdir(parents=True)
        # Latest run configured only security + reliability.
        (latest_dir / "dimensions.json").write_text(
            json.dumps({
                "schema_version": 1,
                "dimensions": {"security": {"state": "done"}, "reliability": {"state": "done"}},
            }),
            encoding="utf-8",
        )
        mock_read.return_value = [
            DimensionResult(dimension="security", overall_score="8.0", source_file_count=10),
            DimensionResult(dimension="reliability", overall_score="7.0"),
            DimensionResult(dimension="performance", overall_score="4.0"),
        ]
        mock_summarize.return_value = type(
            "S", (), {"overall_grade": "A", "numeric_average": 7.5},
        )()

        runs = [RunInfo(run_id="run-new", date_iso="2026-01-02", date_label="Jan 02")]
        _read_accumulated_summary(reports_root, project, runs)

        # summarize_dimensions must see ALL (visible) dims, including the one
        # missing from the latest config.
        called_dims = mock_summarize.call_args[0][0]
        names = sorted(d.dimension for d in called_dims)
        assert names == ["performance", "reliability", "security"], names

    @patch("quodeq.services._fs_metadata.summarize_dimensions")
    @patch("quodeq.services._fs_metadata.read_run_data")
    def test_card_summary_excludes_hidden_standards(
        self, mock_read, mock_summarize, tmp_path, monkeypatch,
    ):
        """Dims outside the visible-standards selection must not move the
        card grade: the Overview headline excludes them (the client filters
        the accumulated payload by the same selection)."""
        from quodeq.core.types import DimensionResult
        from quodeq.data.fs.report_parser.runs import RunInfo
        from quodeq.data.fs.standards_prefs import save_visible_standard_ids

        monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
        reports_root = tmp_path / "evaluations"
        project = "proj"
        (reports_root / project / "run-new").mkdir(parents=True)
        repo = tmp_path / "repo"
        repo.mkdir()
        save_visible_standard_ids(repo, ["security"])
        (reports_root / project / "repository_info.json").write_text(
            json.dumps({"name": project, "path": str(repo), "location": "local"}),
            encoding="utf-8",
        )
        mock_read.return_value = [
            DimensionResult(dimension="Security", overall_score="8.0"),
            DimensionResult(dimension="reliability", overall_score="7.0"),
        ]
        mock_summarize.return_value = type(
            "S", (), {"overall_grade": "A", "numeric_average": 8.0},
        )()

        runs = [RunInfo(run_id="run-new", date_iso="2026-01-02", date_label="Jan 02")]
        _read_accumulated_summary(reports_root, project, runs)

        # Matching is case-insensitive (the selection stores lowercase ids).
        called_dims = mock_summarize.call_args[0][0]
        assert [d.dimension for d in called_dims] == ["Security"]

    @patch("quodeq.services._fs_metadata.summarize_dimensions")
    @patch("quodeq.services._fs_metadata.read_run_data")
    def test_card_summary_default_selection_hides_non_iso_dims(
        self, mock_read, mock_summarize, tmp_path, monkeypatch,
    ):
        """Without a visibility file the six ISO defaults apply, so a retired
        non-default dim (clean-architecture) no longer drags the card grade
        while being invisible on the Overview."""
        from quodeq.core.types import DimensionResult
        from quodeq.data.fs.report_parser.runs import RunInfo

        monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
        reports_root = tmp_path / "evaluations"
        project = "proj"
        (reports_root / project / "run-new").mkdir(parents=True)
        mock_read.return_value = [
            DimensionResult(dimension="security", overall_score="8.0"),
            DimensionResult(dimension="clean-architecture", overall_score="4.0"),
        ]
        mock_summarize.return_value = type(
            "S", (), {"overall_grade": "A", "numeric_average": 8.0},
        )()

        runs = [RunInfo(run_id="run-new", date_iso="2026-01-02", date_label="Jan 02")]
        _read_accumulated_summary(reports_root, project, runs)

        called_dims = mock_summarize.call_args[0][0]
        assert [d.dimension for d in called_dims] == ["security"]

    @patch("quodeq.services._fs_metadata.read_run_data")
    def test_card_summary_recomputes_when_visibility_changes(
        self, mock_read, tmp_path, monkeypatch,
    ):
        """The selection is folded into the cache version: editing
        standards-visibility.json must invalidate the persisted card summary,
        not serve the grade computed under the previous selection."""
        from quodeq.core.types import DimensionResult
        from quodeq.data.fs.report_parser.runs import RunInfo
        from quodeq.data.fs.standards_prefs import save_visible_standard_ids

        monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
        reports_root = tmp_path / "evaluations"
        project = "proj"
        (reports_root / project / "run-new").mkdir(parents=True)
        repo = tmp_path / "repo"
        repo.mkdir()
        (reports_root / project / "repository_info.json").write_text(
            json.dumps({"name": project, "path": str(repo), "location": "local"}),
            encoding="utf-8",
        )
        mock_read.return_value = [
            DimensionResult(dimension="security", overall_score="9.0",
                            overall_grade="Exemplary"),
            DimensionResult(dimension="reliability", overall_score="5.0",
                            overall_grade="Adequate"),
        ]
        runs = [RunInfo(run_id="run-new", date_iso="2026-01-02", date_label="Jan 02")]

        save_visible_standard_ids(repo, ["security", "reliability"])
        _, score_both, _, _ = _read_accumulated_summary(
            reports_root, project, runs, compute_on_miss=True)
        save_visible_standard_ids(repo, ["security"])
        _, score_one, _, _ = _read_accumulated_summary(
            reports_root, project, runs, compute_on_miss=True)

        assert score_both == 7.0
        assert score_one == 9.0

    def test_project_card_reflects_overlaid_sql_grades_and_loaded_params(
        self, tmp_path, monkeypatch,
    ):
        """The project-card summary must reflect the applied grade formula.

        Builds a real event-log run, bakes default grades, applies a custom
        formula, then asserts _read_accumulated_summary (which feeds the
        project card via _build_project_entry) surfaces the CUSTOM grade —
        proving both the read-layer overlay and the loaded-params threading.
        """
        import dataclasses

        from quodeq.core.events.models import Judgment
        from quodeq.core.scoring.params import DEFAULT_PARAMS
        from quodeq.data.fs.report_parser.runs import RunInfo
        from quodeq.data.projection.grade_projector import recompute_grades
        from quodeq.data.sqlite.state_store import SQLiteStateStore
        from quodeq.services import grade_formula
        from quodeq.services.dashboard import clear_shared_dimension_cache

        monkeypatch.setenv("QUODEQ_GRADE_FORMULA_PATH", str(tmp_path / "grade_formula.json"))
        clear_shared_dimension_cache()

        reports_root = tmp_path / "reports"
        project = "proj-uuid"
        run_dir = reports_root / project / "run1"
        run_dir.mkdir(parents=True)
        (run_dir / "events.jsonl").write_text("")

        store = SQLiteStateStore(run_dir)
        for i in range(6):
            store.record_finding(Judgment(
                practice_id="p1", dimension="security", req=f"req{i}",
                verdict="violation", severity="major", file=f"f{i}.py", line=1,
                title=f"t{i}", reason=f"r{i}",
            ))
        for i in range(8):
            store.record_finding(Judgment(
                practice_id="p1", dimension="security", req=f"c{i}",
                verdict="compliance", severity="minor", file=f"g{i}.py", line=1,
                title=f"ct{i}", reason=f"cr{i}",
            ))
        store.save_projected_size((run_dir / "events.jsonl").stat().st_size)
        recompute_grades(run_dir, params=DEFAULT_PARAMS)

        baked = {r["dimension"]: r for r in store.read_dimension_scores()}["security"]
        eval_dir = run_dir / "evaluation"
        eval_dir.mkdir(parents=True, exist_ok=True)
        (eval_dir / "security.json").write_text(json.dumps({
            "schema_version": 1, "dimension": "security", "project": project,
            "discipline": "Python", "date": "2026-05-23", "sourceFileCount": 100,
            "overallScore": f"{baked['score']}/10", "overallGrade": baked["grade"],
            "principles": [], "violations": [], "compliance": [],
            "totals": {"violationCount": 0, "complianceCount": 0, "severity": {}},
        }), encoding="utf-8")

        strict = dataclasses.replace(
            DEFAULT_PARAMS, severity_weight={"critical": 4.0, "major": 6.0, "minor": 0.25},
        )
        grade_formula.save_params(strict)
        grade_formula.apply_to_all_runs(reports_root)
        custom = {r["dimension"]: r for r in store.read_dimension_scores()}["security"]
        assert (custom["score"], custom["grade"]) != (baked["score"], baked["grade"])

        clear_shared_dimension_cache()
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        grade, score, files, _pending = _read_accumulated_summary(
            reports_root, project, runs, compute_on_miss=True)
        clear_shared_dimension_cache()

        # Single dimension → the summary grade/score equals the overlaid custom value.
        assert score == custom["score"]
        assert grade == custom["grade"]
