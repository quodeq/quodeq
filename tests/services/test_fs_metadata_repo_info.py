"""Tests for _fs_metadata.py — path/repo/language-stats/discipline/fingerprint helpers.

Split from test_fs_metadata.py: _check_path_exists, _extract_project_metadata,
_read_repo_info, _read_language_stats, discipline inference, _has_fingerprints.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from quodeq.services._fs_metadata import (
    _check_path_exists,
    _extract_project_metadata,
    _find_discipline_in_run,
    _has_fingerprints,
    _infer_discipline,
    _read_discipline_from_eval,
    _read_language_stats,
    _read_repo_info,
)


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
