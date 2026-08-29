"""Tests for _fs_metadata.py — metadata reading, discipline inference, fingerprints."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.services._fs_metadata import (
    _check_path_exists,
    _extract_project_metadata,
    _find_discipline_in_run,
    _has_fingerprints,
    _infer_discipline,
    _read_accumulated_summary,
    _read_discipline_from_eval,
    _read_language_stats,
    _read_repo_info,
    _read_scan_summary,
)


# ---------------------------------------------------------------------------
# _read_scan_summary
# ---------------------------------------------------------------------------


class TestReadScanSummary:
    def test_reads_scan_data(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "scan.json").write_text(json.dumps({
            "scanned_at": "2026-01-01",
            "total_files": 42,
        }))
        result = _read_scan_summary(tmp_path, "proj")
        assert result["scanDate"] == "2026-01-01"
        assert result["totalFiles"] == 42

    def test_returns_empty_if_missing(self, tmp_path: Path):
        assert _read_scan_summary(tmp_path, "nope") == {}

    def test_returns_empty_on_bad_json(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "scan.json").write_text("bad json")
        assert _read_scan_summary(tmp_path, "proj") == {}


# ---------------------------------------------------------------------------
# _check_path_exists
# ---------------------------------------------------------------------------


class TestCheckPathExists:
    def test_local_existing(self, tmp_path: Path):
        assert _check_path_exists(str(tmp_path), "local") is True

    def test_local_nonexistent(self):
        assert _check_path_exists("/no/such/path", "local") is False

    def test_online_returns_none(self):
        assert _check_path_exists("https://github.com/org/repo", "online") is None

    def test_none_path_returns_none(self):
        assert _check_path_exists(None, "local") is None

    def test_none_location_returns_none(self):
        assert _check_path_exists("/some/path", None) is None


# ---------------------------------------------------------------------------
# _extract_project_metadata
# ---------------------------------------------------------------------------


class TestExtractProjectMetadata:
    def test_extracts_all_fields(self):
        info = {
            "name": "my-project",
            "parent": "parent-uuid",
            "displayName": "My Project",
            "discipline": "software",
            "path": "/path/to/repo",
            "location": "local",
            "scopePath": "src/backend",
        }
        result = _extract_project_metadata(info, "fallback-name")
        assert result["name"] == "my-project"
        assert result["parent"] == "parent-uuid"
        assert result["displayName"] == "My Project"
        assert result["scopePath"] == "src/backend"

    def test_falls_back_to_entry_name(self):
        result = _extract_project_metadata({}, "entry-name")
        assert result["name"] == "entry-name"
        assert result["parent"] is None
        assert result["discipline"] is None


# ---------------------------------------------------------------------------
# _read_repo_info
# ---------------------------------------------------------------------------


class TestReadRepoInfo:
    def test_reads_valid_json(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "repository_info.json").write_text(json.dumps({"name": "test"}))
        result = _read_repo_info(tmp_path, "proj")
        assert result["name"] == "test"

    def test_returns_empty_if_missing(self, tmp_path: Path):
        assert _read_repo_info(tmp_path, "nope") == {}

    def test_returns_empty_on_bad_json(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "repository_info.json").write_text("{bad")
        assert _read_repo_info(tmp_path, "proj") == {}


# ---------------------------------------------------------------------------
# _read_accumulated_summary
# ---------------------------------------------------------------------------


class TestReadAccumulatedSummary:
    @patch("quodeq.services._fs_metadata.read_run_data")
    @patch("quodeq.services._fs_metadata.summarize_dimensions")
    def test_computes_summary(self, mock_summarize, mock_read):
        from quodeq.core.types import DimensionResult
        from quodeq.data.fs.report_parser.runs import RunInfo

        dim = DimensionResult(dimension="security", overall_score="8.5/10",
                              overall_grade="A", files_read=10, source_file_count=10)
        mock_read.return_value = [dim]
        mock_summary = type("S", (), {"overall_grade": "A", "numeric_average": 8.5})()
        mock_summarize.return_value = mock_summary

        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        grade, score, files, _pending = _read_accumulated_summary(
            Path("/r"), "proj", runs, compute_on_miss=True)
        assert grade == "A"
        assert score == 8.5
        assert files == 10

    @patch("quodeq.services._fs_metadata.read_run_data", return_value=[])
    def test_no_dimensions(self, mock_read):
        from quodeq.data.fs.report_parser.runs import RunInfo
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        grade, score, files, _pending = _read_accumulated_summary(
            Path("/r"), "proj", runs, compute_on_miss=True)
        assert grade is None
        assert score is None

    def test_empty_runs(self):
        grade, score, files, pending = _read_accumulated_summary(Path("/r"), "proj", [])
        assert grade is None
        assert score is None
        assert files is None
        assert pending is False

    @patch("quodeq.services._fs_metadata.read_run_data", side_effect=OSError("boom"))
    def test_error_returns_none_tuple(self, mock_read):
        from quodeq.data.fs.report_parser.runs import RunInfo
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        grade, score, files, _pending = _read_accumulated_summary(
            Path("/r"), "proj", runs, compute_on_miss=True)
        assert grade is None
        assert score is None
        assert files is None

    @patch("quodeq.services._fs_metadata.read_run_data", side_effect=KeyError("bad file"))
    def test_keyerror_from_read_path_still_means_no_data(self, mock_read):
        """A malformed run file (adapter KeyError) keeps the 'no data' card."""
        from quodeq.data.fs.report_parser.runs import RunInfo
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        grade, score, files, _pending = _read_accumulated_summary(
            Path("/r"), "proj", runs, compute_on_miss=True)
        assert grade is None
        assert score is None
        assert files is None

    def test_keyerror_from_rescore_propagates_not_masked_as_no_data(self, monkeypatch):
        """A KeyError bug inside the rescoring business rule must surface.

        Historically one except clause wrapped both the file reads and the
        ``_rescore_dimension`` call, so a rescoring bug silently became
        {"grade": None} — indistinguishable from a genuinely missing file.
        """
        from quodeq.core.scoring.params import DEFAULT_PARAMS
        from quodeq.core.types import DimensionResult
        from quodeq.data.fs.report_parser.runs import RunInfo
        from quodeq.services._fs_metadata import _compute_summary

        dim = DimensionResult(dimension="security", overall_score="8.5/10",
                              overall_grade="A", files_read=10, source_file_count=10)
        monkeypatch.setattr("quodeq.services._fs_metadata.read_run_data",
                            lambda *a, **kw: [dim])
        monkeypatch.setattr("quodeq.services.dismissed.dismissed_keys",
                            lambda project_dir: {("REQ-1", "P", "f.py", 1)})
        monkeypatch.setattr("quodeq.services.deleted.deleted_keys",
                            lambda project_dir: set())

        def buggy_rescore(*a, **kw):
            raise KeyError("rescore bug")

        monkeypatch.setattr("quodeq.services.rescore._rescore_dimension", buggy_rescore)
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        with pytest.raises(KeyError, match="rescore bug"):
            _compute_summary(Path("/r"), "proj", runs, DEFAULT_PARAMS, {"security"})

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
        from quodeq.data.fs.standards_prefs import save_visible_standard_ids
        from quodeq.core.types import DimensionResult
        from quodeq.data.fs.report_parser.runs import RunInfo

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
        from quodeq.data.fs.standards_prefs import save_visible_standard_ids
        from quodeq.core.types import DimensionResult
        from quodeq.data.fs.report_parser.runs import RunInfo

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
        from quodeq.data.projection.grade_projector import recompute_grades
        from quodeq.data.sqlite.state_store import SQLiteStateStore
        from quodeq.services import grade_formula
        from quodeq.services.dashboard import clear_shared_dimension_cache
        from quodeq.data.fs.report_parser.runs import RunInfo

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


# ---------------------------------------------------------------------------
# _read_language_stats
# ---------------------------------------------------------------------------


class TestReadLanguageStats:
    def test_reads_from_manifest(self, tmp_path: Path):
        from quodeq.data.fs.report_parser.runs import RunInfo
        proj = tmp_path / "proj" / "run1" / "evidence"
        proj.mkdir(parents=True)
        (proj / "manifest.json").write_text(json.dumps({
            "language_stats": {".py": 100, ".js": 50}
        }))
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        result = _read_language_stats(tmp_path, "proj", runs)
        assert result == {"py": 100, "js": 50}

    def test_strips_leading_dots(self, tmp_path: Path):
        from quodeq.data.fs.report_parser.runs import RunInfo
        proj = tmp_path / "proj" / "run1" / "evidence"
        proj.mkdir(parents=True)
        (proj / "manifest.json").write_text(json.dumps({
            "language_stats": {".ts": 30}
        }))
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        result = _read_language_stats(tmp_path, "proj", runs)
        assert "ts" in result

    def test_returns_empty_on_missing_manifest(self, tmp_path: Path):
        from quodeq.data.fs.report_parser.runs import RunInfo
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        assert _read_language_stats(tmp_path, "proj", runs) == {}

    def test_returns_empty_on_bad_json(self, tmp_path: Path):
        from quodeq.data.fs.report_parser.runs import RunInfo
        proj = tmp_path / "proj" / "run1" / "evidence"
        proj.mkdir(parents=True)
        (proj / "manifest.json").write_text("bad")
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        assert _read_language_stats(tmp_path, "proj", runs) == {}

    def test_skips_empty_stats(self, tmp_path: Path):
        from quodeq.data.fs.report_parser.runs import RunInfo
        proj = tmp_path / "proj" / "run1" / "evidence"
        proj.mkdir(parents=True)
        (proj / "manifest.json").write_text(json.dumps({"language_stats": {}}))
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        assert _read_language_stats(tmp_path, "proj", runs) == {}


# ---------------------------------------------------------------------------
# _read_discipline_from_eval / _find_discipline_in_run / _infer_discipline
# ---------------------------------------------------------------------------


class TestDisciplineInference:
    def test_read_discipline_from_eval(self, tmp_path: Path):
        f = tmp_path / "security_evidence.json"
        f.write_text(json.dumps({"discipline": "software"}))
        assert _read_discipline_from_eval(f) == "software"

    def test_read_discipline_from_eval_missing(self, tmp_path: Path):
        f = tmp_path / "nope.json"
        assert _read_discipline_from_eval(f) is None

    def test_read_discipline_from_eval_bad_json(self, tmp_path: Path):
        f = tmp_path / "bad.json"
        f.write_text("bad")
        assert _read_discipline_from_eval(f) is None

    def test_read_discipline_empty_string(self, tmp_path: Path):
        f = tmp_path / "ev.json"
        f.write_text(json.dumps({"discipline": ""}))
        assert _read_discipline_from_eval(f) is None

    def test_find_discipline_in_run(self, tmp_path: Path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        (evidence_dir / "security_evidence.json").write_text(
            json.dumps({"discipline": "software"})
        )
        assert _find_discipline_in_run(evidence_dir) == "software"

    def test_find_discipline_in_run_none(self, tmp_path: Path):
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        assert _find_discipline_in_run(evidence_dir) is None

    def test_infer_discipline(self, tmp_path: Path):
        proj = tmp_path / "proj"
        run_dir = proj / "20260101" / "evidence"
        run_dir.mkdir(parents=True)
        (run_dir / "sec_evidence.json").write_text(json.dumps({"discipline": "software"}))
        assert _infer_discipline(tmp_path, "proj") == "software"

    def test_infer_discipline_no_runs(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        assert _infer_discipline(tmp_path, "proj") is None


# ---------------------------------------------------------------------------
# _has_fingerprints
# ---------------------------------------------------------------------------


class TestHasFingerprints:
    def test_has_fingerprints(self, tmp_path: Path):
        proj = tmp_path / "proj"
        ev = proj / "run1" / "evidence"
        ev.mkdir(parents=True)
        (ev / "security_fingerprint.json").write_text("{}")
        assert _has_fingerprints(tmp_path, "proj") is True

    def test_no_fingerprints(self, tmp_path: Path):
        proj = tmp_path / "proj"
        ev = proj / "run1" / "evidence"
        ev.mkdir(parents=True)
        (ev / "security_evidence.json").write_text("{}")
        assert _has_fingerprints(tmp_path, "proj") is False

    def test_nonexistent_project(self, tmp_path: Path):
        assert _has_fingerprints(tmp_path, "nope") is False

    def test_no_evidence_dir(self, tmp_path: Path):
        proj = tmp_path / "proj"
        run = proj / "run1"
        run.mkdir(parents=True)
        # No evidence subdir
        assert _has_fingerprints(tmp_path, "proj") is False

    def test_oserror_on_iterdir_logs_warning(self, tmp_path: Path, monkeypatch, caplog):
        """#208 — OSError during dir iteration must be logged, not silently swallowed."""
        import logging
        proj = tmp_path / "proj"
        proj.mkdir()

        def _bad_iterdir(self):
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "iterdir", _bad_iterdir)
        # quodeq logger has propagate=False; enable temporarily so caplog sees records.
        quodeq_logger = logging.getLogger("quodeq")
        orig_propagate = quodeq_logger.propagate
        quodeq_logger.propagate = True
        try:
            with caplog.at_level(logging.WARNING, logger="quodeq.services._fs_metadata"):
                result = _has_fingerprints(tmp_path, "proj")
        finally:
            quodeq_logger.propagate = orig_propagate
        assert result is False
        assert "Could not read fingerprint dir" in caplog.text


class TestCardUsesDefaultViewRuns:
    @patch("quodeq.services._fs_metadata.summarize_dimensions")
    @patch("quodeq.services._fs_metadata.read_run_data")
    def test_newer_noncomplete_run_does_not_drive_the_card(
        self, mock_read, mock_summarize, monkeypatch,
    ):
        """The repositories card must consult the same run set as the
        Overview (select_default_view_runs). It used to iterate ALL runs
        newest-first, so a newer cancelled/failed run gave the card a
        different grade than the Overview showed after clicking in.
        """
        from quodeq.core.types import DimensionResult
        from quodeq.data.fs.report_parser.runs import RunInfo

        monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
        mock_read.return_value = [
            DimensionResult(dimension="security", overall_score="7.0/10",
                            overall_grade="B", files_read=5, source_file_count=5),
        ]
        mock_summarize.return_value = type(
            "S", (), {"overall_grade": "B", "numeric_average": 7.0},
        )()
        runs = [
            RunInfo(run_id="run-cancelled", date_iso="2026-01-03", date_label="Jan 03", status="cancelled"),
            RunInfo(run_id="run-failed", date_iso="2026-01-02", date_label="Jan 02", status="failed"),
            RunInfo(run_id="run-complete", date_iso="2026-01-01", date_label="Jan 01", status="complete"),
        ]
        grade, score, files, _pending = _read_accumulated_summary(
            Path("/r"), "proj-card-eligibility", runs,
        )
        read_run_ids = {call.args[2] for call in mock_read.call_args_list}
        assert read_run_ids == {"run-complete"}, (
            "card must read only the default-view run set, got: "
            f"{read_run_ids}"
        )
        assert grade == "B"

    @patch("quodeq.services._fs_metadata.summarize_dimensions")
    @patch("quodeq.services._fs_metadata.read_run_data")
    def test_card_falls_back_to_cancelled_when_no_complete_run(
        self, mock_read, mock_summarize, monkeypatch,
    ):
        from quodeq.core.types import DimensionResult
        from quodeq.data.fs.report_parser.runs import RunInfo

        monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
        mock_read.return_value = [
            DimensionResult(dimension="security", overall_score="6.0/10",
                            overall_grade="C", files_read=5, source_file_count=5),
        ]
        mock_summarize.return_value = type(
            "S", (), {"overall_grade": "C", "numeric_average": 6.0},
        )()
        runs = [
            RunInfo(run_id="run-cancelled", date_iso="2026-01-02", date_label="Jan 02", status="cancelled"),
            RunInfo(run_id="run-failed", date_iso="2026-01-01", date_label="Jan 01", status="failed"),
        ]
        grade, score, files, _pending = _read_accumulated_summary(
            Path("/r"), "proj-card-fallback", runs,
        )
        read_run_ids = {call.args[2] for call in mock_read.call_args_list}
        assert read_run_ids == {"run-cancelled"}
        assert grade == "C"

    @patch("quodeq.services._fs_metadata.read_run_data")
    def test_card_skips_zero_coverage_stub_like_the_overview(
        self, mock_read, monkeypatch,
    ):
        """A newer cancelled run's coverage-0 stub (filesRead=0) must not
        drive the project card, exactly like the accumulated Overview. The
        card fell through to the real older run's score."""
        from quodeq.core.types import DimensionResult
        from quodeq.data.fs.report_parser.runs import RunInfo

        monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
        per_run = {
            "run-stub": [DimensionResult(
                dimension="security", overall_score="9.9/10", overall_grade="A",
                files_read=0, source_file_count=10,
            )],
            "run-real": [DimensionResult(
                dimension="security", overall_score="6.0/10", overall_grade="C",
                files_read=5, source_file_count=10,
            )],
        }
        mock_read.side_effect = lambda root, proj, run_id: per_run[run_id]
        runs = [
            RunInfo(run_id="run-stub", date_iso="2026-01-02", date_label="Jan 02", status="cancelled"),
            RunInfo(run_id="run-real", date_iso="2026-01-01", date_label="Jan 01", status="cancelled"),
        ]
        grade, score, files, _pending = _read_accumulated_summary(
            Path("/r"), "proj-card-stub", runs,
        )
        # The card score must be the real run's 6.0, not the stub's 9.9.
        assert score == 6.0, f"card took the coverage-0 stub, got {score}"


# ---------------------------------------------------------------------------
# run_dir_by_dim -- each dimension rescored from the run it was SOURCED from
# ---------------------------------------------------------------------------


def _fsm_evidence_line(dim, req, file, line, sev="major", t="violation", p="Confidentiality", vt="VT-COUPLING"):
    """One evidence-jsonl judgment (same shape as test_evidence_rescore.py)."""
    return {"schema_version": 1, "req": req, "t": t, "file": file, "line": line,
            "severity": sev, "w": "title", "reason": f"reason {req} {file} {line}",
            "vt": vt, "p": p, "d": dim}


class TestPerDimensionRunDirRescore:
    """Pins the `run_dir_by_dim` bookkeeping in `_read_accumulated_summary`
    (services/_fs_metadata.py:98-142): on the accumulated/project-card path,
    each dimension must be rescored from the evidence of the run it was
    actually SOURCED from -- not unconditionally from the newest run.
    """

    @patch("quodeq.services._fs_metadata.summarize_dimensions")
    @patch("quodeq.services._fs_metadata.read_run_data")
    def test_dimension_rescored_from_its_sourced_run_not_the_newest(
        self, mock_read, mock_summarize, tmp_path, monkeypatch,
    ):
        from quodeq.core.scoring.params import DEFAULT_PARAMS
        from quodeq.core.types import DimensionResult
        from quodeq.core.types.finding import Finding
        from quodeq.services.dismissed import dismiss_finding, dismissed_keys
        from quodeq.services.evidence_rescore import score_dimension_from_evidence
        from quodeq.data.fs.report_parser.runs import RunInfo

        monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
        reports_root = tmp_path / "evaluations"
        project = "proj-two-run"
        run_old_id, run_new_id = "20260101T000000", "20260102T000000"
        project_dir = reports_root / project
        run_old_dir = project_dir / run_old_id
        run_new_dir = project_dir / run_new_id
        dim_a, dim_b = "security", "reliability"
        sfc, files_read = 10, 5

        # --- dimension A's real evidence lives in the OLDER run: a spread
        # across two principles so a dismissal actually moves the score
        # (mirrors tests/services/test_dashboard_dismiss_consistency.py). ---
        ev_dir_old = run_old_dir / "evidence"
        ev_dir_old.mkdir(parents=True)
        (ev_dir_old / f"{dim_a}_evidence.jsonl").write_text(
            "\n".join(json.dumps(l) for l in [
                _fsm_evidence_line(dim_a, "R-1", "a.kt", 10, sev="major", vt="VT-COUPLING"),
                _fsm_evidence_line(dim_a, "R-2", "a.kt", 20, sev="critical", vt="VT-GODCLASS"),
                _fsm_evidence_line(dim_a, "R-5", "b.kt", 7, sev="major", vt="VT-COUPLING"),
                _fsm_evidence_line(dim_a, "C-1", "a.kt", 1, t="compliance"),
                _fsm_evidence_line(dim_a, "C-3", "b.kt", 3, t="compliance"),
                _fsm_evidence_line(dim_a, "R-4", "c.kt", 9, sev="major", vt="VT-DUPLICATION", p="Integrity"),
                _fsm_evidence_line(dim_a, "C-2", "c.kt", 2, t="compliance", p="Integrity"),
            ]) + "\n", encoding="utf-8",
        )

        # --- dimension B's real evidence lives ONLY in the NEWER run. ---
        ev_dir_new = run_new_dir / "evidence"
        ev_dir_new.mkdir(parents=True)
        (ev_dir_new / f"{dim_b}_evidence.jsonl").write_text(
            "\n".join(json.dumps(l) for l in [
                _fsm_evidence_line(dim_b, "R-10", "x.kt", 3, sev="major", vt="VT-COUPLING", p="Availability"),
                _fsm_evidence_line(dim_b, "C-10", "x.kt", 1, t="compliance", p="Availability"),
            ]) + "\n", encoding="utf-8",
        )

        # The newer run ALSO has evidence for dimension A's filename, but with
        # completely different, unrelated content (none of it matches the
        # dismissal below) -- so if a regression used this dir for dimension A,
        # the dismiss would be a no-op and the rescore would silently reflect
        # this fabricated evidence's own (very different) score instead of the
        # real sourced run's.
        (ev_dir_new / f"{dim_a}_evidence.jsonl").write_text(
            "\n".join(json.dumps(l) for l in [
                _fsm_evidence_line(dim_a, "Z-1", "z.kt", 99, sev="minor", vt="VT-NAMING"),
            ]) + "\n", encoding="utf-8",
        )

        # Scalars read_run_data would report for each run: dim_a's "last
        # valid" occurrence is the OLDER run; dim_b's is the NEWER run.
        per_run = {
            run_new_id: [DimensionResult(
                dimension=dim_b, overall_score="7.0/10", overall_grade="B",
                files_read=files_read, source_file_count=sfc,
                violations=[Finding(req="R-10", file="x.kt", line=3,
                                     practice_id="Availability", severity="major",
                                     dimension=dim_b)],
                compliance=[Finding(req="C-10", file="x.kt", line=1,
                                    practice_id="Availability", dimension=dim_b)],
            )],
            run_old_id: [DimensionResult(
                dimension=dim_a, overall_score="6.0/10", overall_grade="C",
                files_read=files_read, source_file_count=sfc,
                violations=[
                    Finding(req="R-1", file="a.kt", line=10,
                            practice_id="Confidentiality", severity="major", dimension=dim_a),
                    Finding(req="R-2", file="a.kt", line=20,
                            practice_id="Confidentiality", severity="critical", dimension=dim_a),
                    Finding(req="R-5", file="b.kt", line=7,
                            practice_id="Confidentiality", severity="major", dimension=dim_a),
                    Finding(req="R-4", file="c.kt", line=9,
                            practice_id="Integrity", severity="major", dimension=dim_a),
                ],
                compliance=[
                    Finding(req="C-1", file="a.kt", line=1,
                            practice_id="Confidentiality", dimension=dim_a),
                    Finding(req="C-3", file="b.kt", line=3,
                            practice_id="Confidentiality", dimension=dim_a),
                    Finding(req="C-2", file="c.kt", line=2,
                            practice_id="Integrity", dimension=dim_a),
                ],
            )],
        }
        mock_read.side_effect = lambda root, proj, run_id: per_run[run_id]
        mock_summarize.return_value = type(
            "S", (), {"overall_grade": "B", "numeric_average": 6.5},
        )()

        # Dismiss a finding in dimension A (the older run) via the real
        # ActionLogWriter-backed path.
        dismiss_finding(project_dir, {"req": "R-2", "file": "a.kt", "line": 20})
        dismissed = dismissed_keys(project_dir)
        assert dismissed, "dismiss did not register"

        expected = score_dimension_from_evidence(
            run_old_dir, dim_a, dismissed=dismissed, deleted=set(),
            source_file_count=sfc, files_read=files_read, params=DEFAULT_PARAMS,
        )
        assert expected is not None
        assert expected.overall.weighted_score is not None

        # The distinguishing fact: rescoring dim_a from the NEWER run's dir
        # (the wrong-run regression) produces a DIFFERENT, real score -- not
        # merely a missing-evidence None -- so a regression can't be masked
        # by a fallback path silently agreeing with the correct answer.
        wrong = score_dimension_from_evidence(
            run_new_dir, dim_a, dismissed=dismissed, deleted=set(),
            source_file_count=sfc, files_read=files_read, params=DEFAULT_PARAMS,
        )
        assert wrong is not None
        assert wrong.overall.weighted_score != expected.overall.weighted_score, (
            "fixture is not distinguishable: old-run and new-run rescores "
            "of dimension A must differ"
        )

        # Runs passed newest-first, exactly like the real list_runs() order.
        runs = [
            RunInfo(run_id=run_new_id, date_iso="2026-01-02", date_label="Jan 02", status="complete"),
            RunInfo(run_id=run_old_id, date_iso="2026-01-01", date_label="Jan 01", status="complete"),
        ]
        _read_accumulated_summary(reports_root, project, runs, DEFAULT_PARAMS)

        acc_dims = mock_summarize.call_args[0][0]
        dim_a_result = next(d for d in acc_dims if d.dimension == dim_a)
        assert dim_a_result.overall_score == f"{expected.overall.weighted_score}/10", (
            "dimension A must be rescored from the OLDER run it was sourced "
            "from, not from the newest run_dir"
        )
