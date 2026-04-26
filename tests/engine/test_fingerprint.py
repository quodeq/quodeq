"""Tests for evaluation fingerprinting."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from quodeq.analysis.fingerprint import build_fingerprint, find_previous_fingerprint, load_fingerprint, save_fingerprint

_SHA256_HEX_LEN = 64


class TestBuildFingerprint:
    def test_includes_file_hashes(self, tmp_path):
        (tmp_path / "a.py").write_text("content_a")
        (tmp_path / "b.py").write_text("content_b")
        fp = build_fingerprint(src=tmp_path, files=["a.py", "b.py"], dimension="security", standards_dir=None)
        assert "a.py" in fp["file_hashes"]
        assert "b.py" in fp["file_hashes"]
        assert fp["file_hashes"]["a.py"] == hashlib.sha256(b"content_a").hexdigest()

    def test_includes_standards_checksum(self, tmp_path):
        standards = tmp_path / "standards" / "compiled"
        standards.mkdir(parents=True)
        (standards / "security.json").write_text('{"id":"security"}')
        fp = build_fingerprint(src=tmp_path, files=[], dimension="security", standards_dir=tmp_path / "standards")
        assert fp["standards_checksum"] is not None
        assert len(fp["standards_checksum"]) == _SHA256_HEX_LEN

    def test_no_standards_dir(self, tmp_path):
        fp = build_fingerprint(src=tmp_path, files=[], dimension="security", standards_dir=None)
        assert fp["standards_checksum"] is None

    def test_includes_dimension_and_timestamp(self, tmp_path):
        fp = build_fingerprint(src=tmp_path, files=[], dimension="reliability", standards_dir=None)
        assert fp["dimension"] == "reliability"
        assert "timestamp" in fp

    def test_git_commit_included(self, tmp_path):
        fp = build_fingerprint(src=tmp_path, files=[], dimension="security", standards_dir=None)
        assert "git_commit" in fp  # may be None if not a git repo


def test_fingerprint_includes_analyzed_files(tmp_path):
    (tmp_path / "a.py").write_text("print('a')")
    (tmp_path / "b.py").write_text("print('b')")
    fp = build_fingerprint(
        tmp_path, ["a.py", "b.py"], "security", None,
        analyzed_files={"a.py"},
    )
    assert fp["analyzed_files"] == ["a.py"]


def test_fingerprint_without_analyzed_files_defaults_empty(tmp_path):
    (tmp_path / "a.py").write_text("print('a')")
    fp = build_fingerprint(tmp_path, ["a.py"], "security", None)
    assert fp["analyzed_files"] == []


class TestSaveLoadFingerprint:
    def test_round_trip(self, tmp_path):
        fp = {"dimension": "security", "git_commit": "abc", "file_hashes": {"a.py": "hash1"}, "standards_checksum": None, "timestamp": "2026-01-01"}
        save_fingerprint(fp, tmp_path)
        loaded = load_fingerprint(tmp_path, "security")
        assert loaded == fp

    def test_returns_none_when_missing(self, tmp_path):
        assert load_fingerprint(tmp_path, "security") is None


class TestFindPreviousFingerprint:
    def test_returns_none_when_no_previous_runs(self, tmp_path):
        """No previous runs → (None, None)."""
        evidence_dir = tmp_path / "proj" / "run1" / "evidence"
        evidence_dir.mkdir(parents=True)
        fp, prev_dir = find_previous_fingerprint(evidence_dir, "security")
        assert fp is None
        assert prev_dir is None

    def test_returns_none_when_cannot_resolve_paths(self, tmp_path):
        """evidence_dir that doesn't have 'evidence' in path → (None, None)."""
        fp, prev_dir = find_previous_fingerprint(tmp_path, "security")
        assert fp is None
        assert prev_dir is None

    @patch("quodeq.analysis.fingerprint.list_runs")
    def test_finds_fingerprint_from_previous_run(self, mock_list_runs, tmp_path):
        """Previous run has a fingerprint → returns it with evidence dir."""
        from quodeq.data.fs.report_parser.runs import RunInfo

        reports = tmp_path / "reports"
        proj = reports / "proj-uuid"

        # Previous run with fingerprint and completed evaluation report
        prev_run = proj / "run-old"
        prev_evidence = prev_run / "evidence"
        prev_evidence.mkdir(parents=True)
        prev_fp = {"dimension": "security", "file_hashes": {"a.py": "abc123"}, "standards_checksum": None}
        (prev_evidence / "security_fingerprint.json").write_text(json.dumps(prev_fp))
        eval_dir = prev_run / "evaluation"
        eval_dir.mkdir(parents=True)
        (eval_dir / "security.json").write_text("{}")

        # Current run evidence dir
        current_evidence = proj / "run-current" / "evidence"
        current_evidence.mkdir(parents=True)

        # Mock list_runs to return controlled run order
        mock_list_runs.return_value = [
            RunInfo(run_id="run-current", date_iso="2026-03-24T12:00:00Z", date_label=""),
            RunInfo(run_id="run-old", date_iso="2026-03-24T11:00:00Z", date_label=""),
        ]

        fp, prev_dir = find_previous_fingerprint(current_evidence, "security")
        assert fp is not None
        assert fp["file_hashes"]["a.py"] == "abc123"
        assert prev_dir == prev_evidence

    @patch("quodeq.analysis.fingerprint.list_runs")
    def test_accepts_run_without_evaluation_report(self, mock_list_runs, tmp_path):
        """Crashed/cancelled runs without evaluation/{dim}.json should still
        be honoured — the fingerprint they wrote at queue creation is enough
        to anchor the next run's classifier.
        """
        from quodeq.data.fs.report_parser.runs import RunInfo

        reports = tmp_path / "reports"
        proj = reports / "proj-uuid"
        prev_run = proj / "run-cancelled"
        prev_evidence = prev_run / "evidence"
        prev_evidence.mkdir(parents=True)
        prev_fp = {
            "dimension": "usability",
            "file_hashes": {"a.py": "h1", "b.py": "h2"},
            "analyzed_files": ["a.py"],
        }
        (prev_evidence / "usability_fingerprint.json").write_text(json.dumps(prev_fp))
        # Note: NO evaluation/usability.json — run never finalised.

        current_evidence = proj / "run-current" / "evidence"
        current_evidence.mkdir(parents=True)
        mock_list_runs.return_value = [
            RunInfo(run_id="run-current", date_iso="2026-03-24T12:00:00Z", date_label=""),
            RunInfo(run_id="run-cancelled", date_iso="2026-03-24T11:00:00Z", date_label=""),
        ]

        fp, prev_dir = find_previous_fingerprint(current_evidence, "usability")
        assert fp is not None
        assert fp["file_hashes"] == {"a.py": "h1", "b.py": "h2"}
        assert prev_dir == prev_evidence

    @patch("quodeq.analysis.fingerprint.list_runs")
    def test_merges_queue_taken_into_analyzed_files(self, mock_list_runs, tmp_path):
        """Salvage path: when the previous run was cancelled mid-flight, its
        fingerprint's `analyzed_files` is stale (whatever the START state was).
        The queue's taken list reflects the actual work done. Merging the two
        breaks the catch-up loop where every run re-sweeps the same files.
        """
        from quodeq.data.fs.report_parser.runs import RunInfo

        reports = tmp_path / "reports"
        proj = reports / "proj-uuid"
        prev_run = proj / "run-cancelled"
        prev_evidence = prev_run / "evidence"
        prev_evidence.mkdir(parents=True)
        # Fingerprint snapshot from queue creation: 1 file from prior run.
        prev_fp = {
            "dimension": "usability",
            "file_hashes": {f: "h" for f in ["a.py", "b.py", "c.py", "d.py"]},
            "analyzed_files": ["a.py"],
        }
        (prev_evidence / "usability_fingerprint.json").write_text(json.dumps(prev_fp))
        # Queue records that agents took 3 more files before the crash.
        queue = {
            "taken": [
                {"files": ["b.py", "c.py"], "agent": "a1", "ts": 1},
                {"files": ["d.py"], "agent": "a2", "ts": 2},
            ],
            "pending": [],
        }
        (prev_evidence / "usability_queue.json").write_text(json.dumps(queue))

        current_evidence = proj / "run-current" / "evidence"
        current_evidence.mkdir(parents=True)
        mock_list_runs.return_value = [
            RunInfo(run_id="run-current", date_iso="2026-03-24T12:00:00Z", date_label=""),
            RunInfo(run_id="run-cancelled", date_iso="2026-03-24T11:00:00Z", date_label=""),
        ]

        fp, _ = find_previous_fingerprint(current_evidence, "usability")
        assert fp is not None
        assert sorted(fp["analyzed_files"]) == ["a.py", "b.py", "c.py", "d.py"]

    @patch("quodeq.analysis.fingerprint.list_runs")
    def test_queue_merge_is_noop_for_finalized_runs(self, mock_list_runs, tmp_path):
        """A cleanly-finalised run already has queue.taken folded into
        analyzed_files; the salvage merge must not duplicate or perturb it.
        """
        from quodeq.data.fs.report_parser.runs import RunInfo

        reports = tmp_path / "reports"
        proj = reports / "proj-uuid"
        prev_run = proj / "run-old"
        prev_evidence = prev_run / "evidence"
        prev_evidence.mkdir(parents=True)
        prev_fp = {
            "dimension": "security",
            "file_hashes": {"a.py": "h"},
            "analyzed_files": ["a.py", "b.py"],
        }
        (prev_evidence / "security_fingerprint.json").write_text(json.dumps(prev_fp))
        # Queue agrees with fingerprint — typical post-finalisation state.
        queue = {"taken": [{"files": ["a.py", "b.py"], "agent": "a1", "ts": 1}], "pending": []}
        (prev_evidence / "security_queue.json").write_text(json.dumps(queue))

        current_evidence = proj / "run-current" / "evidence"
        current_evidence.mkdir(parents=True)
        mock_list_runs.return_value = [
            RunInfo(run_id="run-current", date_iso="2026-03-24T12:00:00Z", date_label=""),
            RunInfo(run_id="run-old", date_iso="2026-03-24T11:00:00Z", date_label=""),
        ]

        fp, _ = find_previous_fingerprint(current_evidence, "security")
        assert fp is not None
        assert sorted(fp["analyzed_files"]) == ["a.py", "b.py"]

    @patch("quodeq.analysis.fingerprint.list_runs")
    def test_corrupt_queue_is_ignored(self, mock_list_runs, tmp_path):
        """Bad JSON in queue.json must not break the lookup."""
        from quodeq.data.fs.report_parser.runs import RunInfo

        reports = tmp_path / "reports"
        proj = reports / "proj-uuid"
        prev_run = proj / "run-old"
        prev_evidence = prev_run / "evidence"
        prev_evidence.mkdir(parents=True)
        prev_fp = {"dimension": "security", "file_hashes": {}, "analyzed_files": ["a.py"]}
        (prev_evidence / "security_fingerprint.json").write_text(json.dumps(prev_fp))
        (prev_evidence / "security_queue.json").write_text("{not json")

        current_evidence = proj / "run-current" / "evidence"
        current_evidence.mkdir(parents=True)
        mock_list_runs.return_value = [
            RunInfo(run_id="run-current", date_iso="2026-03-24T12:00:00Z", date_label=""),
            RunInfo(run_id="run-old", date_iso="2026-03-24T11:00:00Z", date_label=""),
        ]

        fp, _ = find_previous_fingerprint(current_evidence, "security")
        assert fp is not None
        assert fp["analyzed_files"] == ["a.py"]
