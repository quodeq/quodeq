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
        from quodeq.services.ports import RunInfo

        dim = DimensionResult(dimension="security", source_file_count=10)
        mock_read.return_value = [dim]
        mock_summary = type("S", (), {"overall_grade": "A", "numeric_average": 8.5})()
        mock_summarize.return_value = mock_summary

        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        grade, score, files = _read_accumulated_summary(Path("/r"), "proj", runs)
        assert grade == "A"
        assert score == 8.5
        assert files == 10

    @patch("quodeq.services._fs_metadata.read_run_data", return_value=[])
    def test_no_dimensions(self, mock_read):
        from quodeq.services.ports import RunInfo
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        grade, score, files = _read_accumulated_summary(Path("/r"), "proj", runs)
        assert grade is None
        assert score is None

    def test_empty_runs(self):
        grade, score, files = _read_accumulated_summary(Path("/r"), "proj", [])
        assert grade is None
        assert score is None
        assert files is None

    @patch("quodeq.services._fs_metadata.read_run_data", side_effect=OSError("boom"))
    def test_error_returns_none_tuple(self, mock_read):
        from quodeq.services.ports import RunInfo
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        grade, score, files = _read_accumulated_summary(Path("/r"), "proj", runs)
        assert grade is None
        assert score is None
        assert files is None

    @patch("quodeq.services._fs_metadata.summarize_dimensions")
    @patch("quodeq.services._fs_metadata.read_run_data")
    def test_card_summary_scoped_to_latest_configured_dims(
        self, mock_read, mock_summarize, tmp_path, monkeypatch,
    ):
        """A stale dim (clean-architecture) not configured by the latest run
        is dropped before summarize_dimensions sees it."""
        from quodeq.core.types import DimensionResult
        from quodeq.services.ports import RunInfo

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
            DimensionResult(dimension="clean-architecture", overall_score="4.0"),
        ]
        mock_summarize.return_value = type(
            "S", (), {"overall_grade": "A", "numeric_average": 7.5},
        )()

        runs = [RunInfo(run_id="run-new", date_iso="2026-01-02", date_label="Jan 02")]
        _read_accumulated_summary(reports_root, project, runs)

        # summarize_dimensions must be called WITHOUT clean-architecture.
        called_dims = mock_summarize.call_args[0][0]
        names = sorted(d.dimension for d in called_dims)
        assert names == ["reliability", "security"], names

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
        from quodeq.services.ports import RunInfo

        monkeypatch.setattr(
            grade_formula, "grade_formula_path", lambda: tmp_path / "grade_formula.json",
        )
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
        grade, score, files = _read_accumulated_summary(reports_root, project, runs)
        clear_shared_dimension_cache()

        # Single dimension → the summary grade/score equals the overlaid custom value.
        assert score == custom["score"]
        assert grade == custom["grade"]


# ---------------------------------------------------------------------------
# _read_language_stats
# ---------------------------------------------------------------------------


class TestReadLanguageStats:
    def test_reads_from_manifest(self, tmp_path: Path):
        from quodeq.services.ports import RunInfo
        proj = tmp_path / "proj" / "run1" / "evidence"
        proj.mkdir(parents=True)
        (proj / "manifest.json").write_text(json.dumps({
            "language_stats": {".py": 100, ".js": 50}
        }))
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        result = _read_language_stats(tmp_path, "proj", runs)
        assert result == {"py": 100, "js": 50}

    def test_strips_leading_dots(self, tmp_path: Path):
        from quodeq.services.ports import RunInfo
        proj = tmp_path / "proj" / "run1" / "evidence"
        proj.mkdir(parents=True)
        (proj / "manifest.json").write_text(json.dumps({
            "language_stats": {".ts": 30}
        }))
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        result = _read_language_stats(tmp_path, "proj", runs)
        assert "ts" in result

    def test_returns_empty_on_missing_manifest(self, tmp_path: Path):
        from quodeq.services.ports import RunInfo
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        assert _read_language_stats(tmp_path, "proj", runs) == {}

    def test_returns_empty_on_bad_json(self, tmp_path: Path):
        from quodeq.services.ports import RunInfo
        proj = tmp_path / "proj" / "run1" / "evidence"
        proj.mkdir(parents=True)
        (proj / "manifest.json").write_text("bad")
        runs = [RunInfo(run_id="run1", date_iso="2026-01-01", date_label="Jan 01")]
        assert _read_language_stats(tmp_path, "proj", runs) == {}

    def test_skips_empty_stats(self, tmp_path: Path):
        from quodeq.services.ports import RunInfo
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
