"""Tests for incremental fingerprint saving and backfill verification."""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

from quodeq.analysis._incremental import save_dimension_fingerprint
from quodeq.analysis._backfill import run_backfill_phase, BackfillContext


class TestSaveDimensionFingerprintJsonlUnion:
    @patch("quodeq.analysis._incremental_evidence._list_source_files")
    @patch("quodeq.analysis._incremental_evidence.save_fingerprint")
    @patch("quodeq.analysis._incremental_evidence.build_fingerprint")
    def test_includes_files_from_jsonl_not_in_queue(
        self, mock_build, mock_save, mock_list_files, tmp_path,
    ):
        """Files in JSONL but not in queue are included in analyzed_files."""
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()

        # Queue has only file_a
        queue_data = {
            "version": 1,
            "pending": [],
            "taken": [{"files": ["a.py"], "agent": "agent-0", "ts": 1.0}],
        }
        (evidence_dir / "security_queue.json").write_text(json.dumps(queue_data))

        # JSONL has file_a and file_b (file_b came from verification carry-forward)
        (evidence_dir / "security_evidence.jsonl").write_text(
            '{"p":"Mod","t":"violation","file":"a.py","line":1}\n'
            '{"p":"Mod","t":"violation","file":"b.py","line":1}\n'
        )

        mock_list_files.return_value = (["a.py", "b.py", "c.py"], set())
        mock_build.return_value = {"dimension": "security"}

        config = MagicMock()
        config.work_dir = evidence_dir
        config.src = tmp_path
        config.options.incremental_file_filter = None
        config.standards_dir = None

        save_dimension_fingerprint(config, "security")

        # build_fingerprint should receive analyzed_files containing both a.py and b.py
        call_kwargs = mock_build.call_args
        analyzed = call_kwargs.kwargs.get("analyzed_files") or call_kwargs[1].get("analyzed_files")
        assert "a.py" in analyzed
        assert "b.py" in analyzed
        assert "c.py" not in analyzed  # not in queue or JSONL

    @patch("quodeq.analysis._incremental_evidence._list_source_files")
    @patch("quodeq.analysis._incremental_evidence.save_fingerprint")
    @patch("quodeq.analysis._incremental_evidence.build_fingerprint")
    def test_no_duplicates_in_union(
        self, mock_build, mock_save, mock_list_files, tmp_path,
    ):
        """Files in both queue and JSONL produce a clean set (no duplicates)."""
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()

        queue_data = {
            "version": 1,
            "pending": [],
            "taken": [{"files": ["a.py", "b.py"], "agent": "agent-0", "ts": 1.0}],
        }
        (evidence_dir / "security_queue.json").write_text(json.dumps(queue_data))

        (evidence_dir / "security_evidence.jsonl").write_text(
            '{"p":"Mod","t":"violation","file":"a.py","line":1}\n'
            '{"p":"Mod","t":"violation","file":"b.py","line":1}\n'
        )

        mock_list_files.return_value = (["a.py", "b.py"], set())
        mock_build.return_value = {"dimension": "security"}

        config = MagicMock()
        config.work_dir = evidence_dir
        config.src = tmp_path
        config.options.incremental_file_filter = None
        config.standards_dir = None

        save_dimension_fingerprint(config, "security")

        call_kwargs = mock_build.call_args
        analyzed = call_kwargs.kwargs.get("analyzed_files") or call_kwargs[1].get("analyzed_files")
        assert analyzed == {"a.py", "b.py"}


class TestBackfillSkipsVerification:
    @patch("quodeq.analysis._dimension_ops._process_single_dimension")
    def test_verify_findings_disabled_during_backfill(self, mock_process, tmp_path):
        """Backfill disables verify_findings before calling _process_single_dimension."""
        config = MagicMock()
        config.options.pool_budget = 600
        config.options.verify_findings = True
        config.options.incremental_file_filter = None

        captured_verify = []

        def capture_config(*args, **kwargs):
            captured_verify.append(config.options.verify_findings)

        mock_process.side_effect = capture_config

        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()

        ctx = MagicMock()
        backfill_ctx = BackfillContext(
            files=["a.py", "b.py", "c.py"],
            prev_analyzed=set(),
            phase1_files=set(),
            evidence_dir=evidence_dir,
            phase_start=time.monotonic() - 10,  # 10s elapsed, plenty of budget
        )

        run_backfill_phase(config, "security", 1, ctx, backfill_ctx)

        # verify_findings should have been False when _process_single_dimension was called
        assert captured_verify == [False]
        # verify_findings should be restored after
        assert config.options.verify_findings is True

    @patch("quodeq.analysis._dimension_ops._process_single_dimension")
    def test_verify_findings_restored_on_error(self, mock_process, tmp_path):
        """verify_findings is restored even if _process_single_dimension raises."""
        config = MagicMock()
        config.options.pool_budget = 600
        config.options.verify_findings = True
        config.options.incremental_file_filter = None

        mock_process.side_effect = RuntimeError("boom")

        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()

        ctx = MagicMock()
        backfill_ctx = BackfillContext(
            files=["a.py"],
            prev_analyzed=set(),
            phase1_files=set(),
            evidence_dir=evidence_dir,
            phase_start=time.monotonic() - 10,
        )

        try:
            run_backfill_phase(config, "security", 1, ctx, backfill_ctx)
        except RuntimeError:
            pass

        assert config.options.verify_findings is True
