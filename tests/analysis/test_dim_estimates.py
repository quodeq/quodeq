"""Tests for quodeq.analysis._dim_estimates — upfront per-dim file estimation."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from quodeq.analysis._dim_estimates import (
    DIM_ESTIMATES_FILENAME,
    compute_dim_estimates,
    read_dim_estimates,
    write_dim_estimates,
)
from quodeq.analysis._incr_change_detection import ChangeDetectionResult
from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.analysis.incremental import FileClassification


def _make_config(*, incremental: bool = False, file_filter=None) -> RunConfig:
    """Minimal RunConfig stub. Only fields read by compute_dim_estimates matter."""
    cfg = RunConfig.__new__(RunConfig)
    cfg.src = Path("/repo")
    cfg.standards_dir = None
    cfg.work_dir = None
    cfg.language = "python"
    options = type("O", (), {})()
    options.incremental = incremental
    options.incremental_file_filter = file_filter
    cfg.options = options
    return cfg


class TestComputeDimEstimates:
    def test_full_run_returns_per_dim_file_count(self) -> None:
        cfg = _make_config()
        with patch(
            "quodeq.analysis._dim_estimates._list_all_source_files",
            side_effect=lambda config, dim: {
                "security": ["a.py", "b.py", "c.py"],
                "reliability": ["a.py", "b.py"],
            }[dim],
        ):
            estimates = compute_dim_estimates(cfg, ["security", "reliability"])
        assert estimates == {
            "security": {"count": 3, "reason": "full"},
            "reliability": {"count": 2, "reason": "full"},
        }

    def test_empty_dim_returns_zero_with_empty_reason(self) -> None:
        cfg = _make_config()
        with patch(
            "quodeq.analysis._dim_estimates._list_all_source_files",
            return_value=[],
        ):
            estimates = compute_dim_estimates(cfg, ["security"])
        assert estimates == {"security": {"count": 0, "reason": "empty"}}

    def test_diff_mode_intersects_filter(self) -> None:
        cfg = _make_config(file_filter={"a.py", "c.py"})
        with patch(
            "quodeq.analysis._dim_estimates._list_all_source_files",
            return_value=["a.py", "b.py", "c.py", "d.py"],
        ):
            estimates = compute_dim_estimates(cfg, ["security"])
        assert estimates == {"security": {"count": 2, "reason": "diff"}}

    def test_incremental_normal_run(self) -> None:
        cfg = _make_config(incremental=True)
        files = ["a.py", "b.py", "c.py", "d.py"]
        prev_fp = {"file_hashes": {f: "h" for f in files}, "analyzed_files": files}
        with patch(
            "quodeq.analysis._dim_estimates._list_all_source_files",
            return_value=files,
        ), patch(
            "quodeq.analysis._dim_estimates.find_previous_fingerprint",
            return_value=(prev_fp, Path("/prev")),
        ), patch(
            "quodeq.analysis._dim_estimates.detect_changed_files",
            return_value=ChangeDetectionResult(changed={"a.py"}),
        ), patch(
            "quodeq.analysis._dim_estimates.classify_files",
            return_value=FileClassification(to_analyze=["a.py", "b.py"], unchanged={"c.py", "d.py"}),
        ):
            estimates = compute_dim_estimates(cfg, ["security"])
        assert estimates == {"security": {"count": 2, "reason": "incremental"}}

    def test_incremental_first_run_marks_first_run(self) -> None:
        cfg = _make_config(incremental=True)
        files = ["a.py", "b.py"]
        with patch(
            "quodeq.analysis._dim_estimates._list_all_source_files",
            return_value=files,
        ), patch(
            "quodeq.analysis._dim_estimates.find_previous_fingerprint",
            return_value=(None, None),
        ), patch(
            "quodeq.analysis._dim_estimates.detect_changed_files",
            return_value=ChangeDetectionResult(full_reanalysis=True, reason="no previous fingerprint"),
        ), patch(
            "quodeq.analysis._dim_estimates.classify_files",
            return_value=FileClassification(to_analyze=files, full_reanalysis=True),
        ):
            estimates = compute_dim_estimates(cfg, ["security"])
        assert estimates == {"security": {"count": 2, "reason": "first-run"}}

    def test_incremental_standards_changed(self) -> None:
        cfg = _make_config(incremental=True)
        files = ["a.py", "b.py"]
        with patch(
            "quodeq.analysis._dim_estimates._list_all_source_files",
            return_value=files,
        ), patch(
            "quodeq.analysis._dim_estimates.find_previous_fingerprint",
            return_value=({"file_hashes": {}}, Path("/prev")),
        ), patch(
            "quodeq.analysis._dim_estimates.detect_changed_files",
            return_value=ChangeDetectionResult(full_reanalysis=True, reason="standards changed"),
        ), patch(
            "quodeq.analysis._dim_estimates.classify_files",
            return_value=FileClassification(to_analyze=files, full_reanalysis=True),
        ):
            estimates = compute_dim_estimates(cfg, ["security"])
        assert estimates["security"]["reason"] == "standards-changed"

    def test_incremental_catching_up_when_prior_run_died_early(self) -> None:
        # Prior run fingerprinted 100 files but only analyzed 20 → < 50%
        # threshold → marked as catching-up so the UI can flag the inflated
        # count as catch-up work, not a code growth signal.
        cfg = _make_config(incremental=True)
        files = [f"f{i}.py" for i in range(100)]
        prev_fp = {
            "file_hashes": {f: "h" for f in files},
            "analyzed_files": files[:20],
        }
        with patch(
            "quodeq.analysis._dim_estimates._list_all_source_files",
            return_value=files,
        ), patch(
            "quodeq.analysis._dim_estimates.find_previous_fingerprint",
            return_value=(prev_fp, Path("/prev")),
        ), patch(
            "quodeq.analysis._dim_estimates.detect_changed_files",
            return_value=ChangeDetectionResult(changed=set(files[20:])),
        ), patch(
            "quodeq.analysis._dim_estimates.classify_files",
            return_value=FileClassification(to_analyze=files[20:], unchanged=set(files[:20])),
        ):
            estimates = compute_dim_estimates(cfg, ["usability"])
        assert estimates["usability"]["reason"] == "catching-up"
        assert estimates["usability"]["count"] == 80


class TestFreshRunSafety:
    """Regression guards for the incremental=True default with no prior data.

    After Task 1's default flip, compute_dim_estimates runs the incremental
    branch on every default run. These tests confirm that first-ever runs
    (no prior fingerprint, no prior queue) do not crash.
    """

    def test_dim_estimates_no_prior_run_is_safe(self) -> None:
        """With incremental=True (default) and no prior fingerprint, dim estimates run cleanly."""
        # Use real AnalysisOptions() so this test breaks if the default reverts.
        cfg = RunConfig.__new__(RunConfig)
        cfg.src = Path("/repo")
        cfg.standards_dir = None
        cfg.work_dir = None
        cfg.language = "python"
        cfg.options = AnalysisOptions()  # incremental=True by default
        assert cfg.options.incremental is True

        files = ["a.py", "b.py"]
        with patch(
            "quodeq.analysis._dim_estimates._list_all_source_files",
            return_value=files,
        ), patch(
            "quodeq.analysis._dim_estimates.find_previous_fingerprint",
            return_value=(None, None),  # fresh run: no prior fingerprint
        ), patch(
            "quodeq.analysis._dim_estimates.detect_changed_files",
            return_value=ChangeDetectionResult(full_reanalysis=True, reason="no previous fingerprint"),
        ), patch(
            "quodeq.analysis._dim_estimates.classify_files",
            return_value=FileClassification(to_analyze=files, full_reanalysis=True),
        ):
            # Must not raise even with no prior fingerprint.
            estimates = compute_dim_estimates(cfg, ["security"])

        assert estimates == {"security": {"count": 2, "reason": "first-run"}}


class TestPersistence:
    def test_write_then_read_roundtrip(self, tmp_path: Path) -> None:
        payload = {
            "security": {"count": 42, "reason": "incremental"},
            "usability": {"count": 999, "reason": "catching-up"},
        }
        write_dim_estimates(tmp_path, payload)
        assert read_dim_estimates(tmp_path) == payload

    def test_read_missing_returns_empty(self, tmp_path: Path) -> None:
        assert read_dim_estimates(tmp_path) == {}

    def test_read_corrupt_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / DIM_ESTIMATES_FILENAME).write_text("not json{", encoding="utf-8")
        assert read_dim_estimates(tmp_path) == {}

    def test_read_skips_malformed_entries(self, tmp_path: Path) -> None:
        (tmp_path / DIM_ESTIMATES_FILENAME).write_text(
            json.dumps({
                "good": {"count": 5, "reason": "incremental"},
                "missing_count": {"reason": "incremental"},
                "wrong_count_type": {"count": "oops", "reason": "incremental"},
                "wrong_value_type": "oops",
                "legacy_int": 7,
            }),
            encoding="utf-8",
        )
        # legacy_int is accepted (back-compat); the others are dropped.
        assert read_dim_estimates(tmp_path) == {
            "good": {"count": 5, "reason": "incremental"},
            "legacy_int": {"count": 7, "reason": ""},
        }

    def test_read_non_dict_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / DIM_ESTIMATES_FILENAME).write_text(
            json.dumps([1, 2, 3]), encoding="utf-8",
        )
        assert read_dim_estimates(tmp_path) == {}

    def test_read_defaults_missing_reason_to_empty_string(self, tmp_path: Path) -> None:
        (tmp_path / DIM_ESTIMATES_FILENAME).write_text(
            json.dumps({"security": {"count": 5}}), encoding="utf-8",
        )
        assert read_dim_estimates(tmp_path) == {"security": {"count": 5, "reason": ""}}
