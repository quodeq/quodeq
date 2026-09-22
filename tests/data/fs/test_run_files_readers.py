"""Run-directory evidence/queue readers and discard-time cleanup mechanics.

These back services/score_run (salvage scoring after cancellation) and
services/evaluation_mixin (discard). Everything is best-effort: an
unreadable file degrades to "no signal" or a logged skip, never a raise.
"""
from __future__ import annotations

import json

from quodeq.data.fs.run_files import (
    dimension_queue_file,
    list_dimension_evidence,
    queue_file_exists,
    read_dispatched_cache_keys,
    read_queue_files_count,
    remove_matching_files,
)


def _seed_run(tmp_path):
    run_dir = tmp_path / "run1"
    (run_dir / "evidence").mkdir(parents=True)
    return run_dir


class TestListDimensionEvidence:
    def test_none_when_evidence_dir_absent(self, tmp_path):
        assert list_dimension_evidence(tmp_path / "run1") is None

    def test_empty_when_no_evidence_files(self, tmp_path):
        run_dir = _seed_run(tmp_path)
        assert list_dimension_evidence(run_dir) == []

    def test_entries_carry_dim_id_path_and_size(self, tmp_path):
        run_dir = _seed_run(tmp_path)
        (run_dir / "evidence" / "security_evidence.jsonl").write_text('{"f":1}\n')
        (run_dir / "evidence" / "maintainability_evidence.jsonl").write_text("")
        (run_dir / "evidence" / "security_queue.json").write_text("{}")

        entries = sorted(list_dimension_evidence(run_dir))
        assert [(d, s > 0) for d, _p, s in entries] == [
            ("maintainability", False), ("security", True),
        ]
        assert entries[1][1] == run_dir / "evidence" / "security_evidence.jsonl"


class TestQueueFile:
    def test_exists_and_path(self, tmp_path):
        run_dir = _seed_run(tmp_path)
        assert queue_file_exists(run_dir, "security") is False
        dimension_queue_file(run_dir, "security").write_text("{}")
        assert queue_file_exists(run_dir, "security") is True


class TestReadQueueFilesCount:
    def test_sums_files_across_batches(self, tmp_path):
        queue = tmp_path / "q.json"
        queue.write_text(json.dumps({
            "taken": [
                {"files": ["a.py", "b.py"], "agent": "a1", "ts": 1},
                {"files": ["c.py"], "agent": "a2", "ts": 2},
            ],
        }))
        assert read_queue_files_count(queue) == 3

    def test_zero_when_missing_corrupt_or_malformed(self, tmp_path):
        assert read_queue_files_count(tmp_path / "missing.json") == 0
        corrupt = tmp_path / "c.json"
        corrupt.write_text("{nope")
        assert read_queue_files_count(corrupt) == 0
        malformed = tmp_path / "m.json"
        malformed.write_text(json.dumps({"taken": [{"agent": "a1"}, {"files": ["x.py"]}]}))
        assert read_queue_files_count(malformed) == 1


class TestReadDispatchedCacheKeys:
    def test_collects_values_from_all_sidecars(self, tmp_path):
        (tmp_path / "d1_dispatch_keys.json").write_text(json.dumps({"a.py": "k1", "b.py": "k2"}))
        (tmp_path / "d2_dispatch_keys.json").write_text(json.dumps({"c.py": "k3"}))
        assert sorted(read_dispatched_cache_keys(tmp_path)) == ["k1", "k2", "k3"]

    def test_skips_unreadable_and_non_dict_sidecars(self, tmp_path):
        (tmp_path / "bad_dispatch_keys.json").write_text("{nope")
        (tmp_path / "list_dispatch_keys.json").write_text("[1, 2]")
        (tmp_path / "ok_dispatch_keys.json").write_text(json.dumps({"a.py": "k9"}))
        assert read_dispatched_cache_keys(tmp_path) == ["k9"]

    def test_ignores_replayed_keys_sidecars(self, tmp_path):
        # These belong to EARLIER runs; discarding this run must not
        # collect their cache keys for deletion.
        (tmp_path / "d_replayed_unconsolidated_keys.json").write_text(
            json.dumps({"a.py": "theirs"}),
        )
        assert read_dispatched_cache_keys(tmp_path) == []


class TestRemoveMatchingFiles:
    def test_removes_only_matching_files(self, tmp_path):
        (tmp_path / "d_queue.json").write_text("{}")
        (tmp_path / "d_evidence.jsonl").write_text("")
        keeper = tmp_path / "manifest.json"
        keeper.write_text("{}")

        remove_matching_files(tmp_path, ("*_queue.json", "*_evidence.jsonl"))

        assert not (tmp_path / "d_queue.json").exists()
        assert not (tmp_path / "d_evidence.jsonl").exists()
        assert keeper.exists()

    def test_tolerates_no_matches(self, tmp_path):
        remove_matching_files(tmp_path, ("*_queue.json",))
