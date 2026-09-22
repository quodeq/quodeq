"""Tests for evaluation_mixin.py — score_completed_evidence and list_evaluations.

Split from test_evaluation_mixin.py."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from quodeq.services.base import (
    EvaluationOptions,
)
from quodeq.services.evaluation_mixin import (
    FsEvaluationMixin,
)
from quodeq.services.score_run import (
    _read_project_source_file_count,
    _read_queue_files_count,
)
from quodeq.services.score_run import (
    score_completed_evidence as _score_completed_evidence,
)


class TestScoreCompletedEvidence:
    def test_noop_without_project(self):
        _score_completed_evidence("/reports", {})  # should not raise

    def test_noop_without_run_id(self):
        _score_completed_evidence("/reports", {"outputProject": "proj"})

    def test_noop_without_evidence_dir(self, tmp_path: Path):
        reports = tmp_path / "reports"
        reports.mkdir()
        _score_completed_evidence(str(reports), {
            "outputProject": "proj",
            "outputRunId": "run1",
        })  # evidence dir does not exist

    def test_skips_already_scored(self, tmp_path: Path):
        reports = tmp_path / "reports"
        proj_dir = reports / "proj" / "run1"
        evidence_dir = proj_dir / "evidence"
        eval_dir = proj_dir / "evaluation"
        evidence_dir.mkdir(parents=True)
        eval_dir.mkdir(parents=True)
        # Create evidence + already-existing eval
        (evidence_dir / "security_evidence.jsonl").write_text('{"finding": 1}\n')
        (evidence_dir / "security_queue.json").write_text("[]")
        (eval_dir / "security.json").write_text("{}")
        _score_completed_evidence(str(reports), {
            "outputProject": "proj",
            "outputRunId": "run1",
        })
        # Should not crash and existing eval remains

    def test_skips_empty_evidence(self, tmp_path: Path):
        reports = tmp_path / "reports"
        evidence_dir = reports / "proj" / "run1" / "evidence"
        evidence_dir.mkdir(parents=True)
        (evidence_dir / "security_evidence.jsonl").write_text("")
        (evidence_dir / "security_queue.json").write_text("[]")
        _score_completed_evidence(str(reports), {
            "outputProject": "proj",
            "outputRunId": "run1",
        })

    def test_skips_without_queue_file(self, tmp_path: Path):
        reports = tmp_path / "reports"
        evidence_dir = reports / "proj" / "run1" / "evidence"
        evidence_dir.mkdir(parents=True)
        (evidence_dir / "security_evidence.jsonl").write_text('{"f": 1}\n')
        # No queue file
        _score_completed_evidence(str(reports), {
            "outputProject": "proj",
            "outputRunId": "run1",
        })


# ---------------------------------------------------------------------------
# _read_queue_files_count + _read_project_source_file_count
# ---------------------------------------------------------------------------

class TestReadQueueFilesCount:
    """Pin the contract that salvage scoring uses to populate `files_read`.

    Without this, ``_score_completed_evidence`` writes evals with
    ``filesRead: 0`` — which the ``scoring_view`` trust rule rejects as
    untrustworthy stubs, falling the user back to an older run's stale
    score for that dim despite real findings being on disk.
    """

    def test_sums_files_across_taken_batches(self, tmp_path: Path):
        # Real-shape queue: each batch is `{files, agent, ts}`; files_read
        # is the count of files dispatched across all batches.
        queue = tmp_path / "q.json"
        queue.write_text(json.dumps({
            "taken": [
                {"files": ["a.py", "b.py", "c.py"], "agent": "a1", "ts": 1},
                {"files": ["d.py", "e.py"], "agent": "a2", "ts": 2},
            ],
            "pending": [],
        }))
        assert _read_queue_files_count(queue) == 5

    def test_zero_when_no_taken_entries(self, tmp_path: Path):
        queue = tmp_path / "q.json"
        queue.write_text(json.dumps({"taken": [], "pending": ["x.py"]}))
        assert _read_queue_files_count(queue) == 0

    def test_zero_when_missing_file(self, tmp_path: Path):
        # Salvage path encounters a non-existent queue (rare but possible
        # if a dim never reached the queue-creation step) — must not raise.
        assert _read_queue_files_count(tmp_path / "missing.json") == 0

    def test_zero_when_corrupt_json(self, tmp_path: Path):
        queue = tmp_path / "q.json"
        queue.write_text("{not json")
        assert _read_queue_files_count(queue) == 0

    def test_handles_missing_files_field_in_batch(self, tmp_path: Path):
        # Defensive: a malformed batch missing `files` shouldn't crash.
        queue = tmp_path / "q.json"
        queue.write_text(json.dumps({
            "taken": [{"agent": "a1", "ts": 1}, {"files": ["x.py"]}],
            "pending": [],
        }))
        assert _read_queue_files_count(queue) == 1


class TestReadProjectSourceFileCount:
    def test_reads_from_scan_json(self, tmp_path: Path):
        proj_dir = tmp_path / "reports" / "proj"
        proj_dir.mkdir(parents=True)
        (proj_dir / "scan.json").write_text(json.dumps({"total_files": 1855}))
        assert _read_project_source_file_count(str(tmp_path / "reports"), "proj") == 1855

    def test_zero_when_scan_missing(self, tmp_path: Path):
        assert _read_project_source_file_count(str(tmp_path), "ghost") == 0

    def test_zero_when_corrupt_scan(self, tmp_path: Path):
        proj_dir = tmp_path / "reports" / "proj"
        proj_dir.mkdir(parents=True)
        (proj_dir / "scan.json").write_text("{nope")
        assert _read_project_source_file_count(str(tmp_path / "reports"), "proj") == 0

    def test_zero_when_total_files_not_int(self, tmp_path: Path):
        proj_dir = tmp_path / "reports" / "proj"
        proj_dir.mkdir(parents=True)
        (proj_dir / "scan.json").write_text(json.dumps({"total_files": "many"}))
        assert _read_project_source_file_count(str(tmp_path / "reports"), "proj") == 0


class TestScoreCompletedEvidencePopulatesCoverage:
    """The bug this fixes: salvage-written evals had filesRead=0, so the
    scoring_view trust rule (filesRead > 0) rejected them as stubs. The
    user-visible symptom was a real, fully-completed dim's score being
    silently replaced by an older run's score on the overview cards.
    """

    def test_files_read_populated_from_queue(self, tmp_path: Path):
        reports = tmp_path / "reports"
        proj = reports / "proj"
        run = proj / "run1"
        ev_dir = run / "evidence"
        ev_dir.mkdir(parents=True)
        # Mark the project's scan with a real total_files.
        (proj / "scan.json").write_text(json.dumps({"total_files": 1000}))
        # 7 files dispatched across two agent batches.
        (ev_dir / "security_queue.json").write_text(json.dumps({
            "taken": [
                {"files": ["a.py", "b.py", "c.py", "d.py"], "agent": "a1", "ts": 1},
                {"files": ["e.py", "f.py", "g.py"], "agent": "a2", "ts": 2},
            ],
            "pending": [],
        }))
        # Real findings written to JSONL (would normally come from agents).
        (ev_dir / "security_evidence.jsonl").write_text(
            '{"req": "S-CON-1", "t": "violation", "file": "a.py", "line": 1, "severity": "minor", "w": "x", "reason": "y"}\n'
        )

        _score_completed_evidence(str(reports), {
            "outputProject": "proj",
            "outputRunId": "run1",
        })

        eval_path = run / "evaluation" / "security.json"
        assert eval_path.is_file()
        eval_data = json.loads(eval_path.read_text())
        # The fix: filesRead reflects the queue's taken count, not 0.
        assert eval_data["filesRead"] == 7
        # And source_file_count comes from scan.json.
        assert eval_data["sourceFileCount"] == 1000

    def test_files_read_zero_when_no_queue(self, tmp_path: Path):
        # Edge case: if the queue file is missing entirely (which already
        # short-circuits the dim earlier in the function), the helper
        # gracefully returns 0 without crashing the broader walk.
        reports = tmp_path / "reports"
        ev_dir = reports / "proj" / "run1" / "evidence"
        ev_dir.mkdir(parents=True)
        # No queue file — _score_completed_evidence skips this dim entirely.
        (ev_dir / "security_evidence.jsonl").write_text('{"f":1}\n')
        _score_completed_evidence(str(reports), {
            "outputProject": "proj",
            "outputRunId": "run1",
        })
        eval_path = reports / "proj" / "run1" / "evaluation" / "security.json"
        assert not eval_path.exists()  # skipped because no queue


# ---------------------------------------------------------------------------
# list_evaluations
# ---------------------------------------------------------------------------


class TestListEvaluations:
    def test_delegates_to_job_manager(self):
        m = FsEvaluationMixin()
        m._jobs = MagicMock()
        m._jobs.list_jobs.return_value = []
        assert m.list_evaluations() == []


def test_evaluation_options_clean_scan_field_defaults_false():
    """User-facing flag: clean_scan opts OUT of cache; default behaviour is incremental."""
    opts = EvaluationOptions()
    assert opts.clean_scan is False
    assert not hasattr(opts, "incremental"), (
        "Old field name leaked through; rename incomplete."
    )
