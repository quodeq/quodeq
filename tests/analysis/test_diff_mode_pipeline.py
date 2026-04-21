"""Pipeline dispatch for diff mode — must skip incremental loop and fingerprint save."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from quodeq.analysis._pipeline import _run_dimensions
from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.analysis.manifest_models import SourceManifest
from quodeq.core.evidence.model import Evidence


def _minimal_config(diff_from: str | None, skip_scoring: bool, incremental: bool = False) -> RunConfig:
    manifest = SourceManifest()
    return RunConfig(
        src=Path("/tmp"),
        language="python",
        manifest=manifest,
        dimensions_data={"applies": [{"id": "security"}]},
        options=AnalysisOptions(
            diff_from=diff_from,
            skip_scoring=skip_scoring,
            incremental=incremental,
            incremental_file_filter={"a.py"} if diff_from else None,
            consolidated=False,
            max_subagents=1,
        ),
    )


def _fake_evidence() -> Evidence:
    return Evidence(
        repository="/tmp",
        language="python",
        date="2026-04-21T00:00:00+00:00",
        source_file_count=1,
        files_read=1,
        coverage_pct=100.0,
    )


def test_diff_mode_uses_per_dimension_loop_not_incremental() -> None:
    """diff_from set: the incremental loop must NOT be used (no baseline)."""
    config = _minimal_config(diff_from="main", skip_scoring=True)
    with patch("quodeq.analysis._pipeline.run_incremental_loop") as incr, \
         patch("quodeq.analysis._pipeline.run_per_dimension_loop") as per, \
         patch("quodeq.analysis._pipeline.load_analysis_context") as ctx:
        ctx.return_value = (["security"], type("C", (), {"total": 1})())
        per.return_value = {"security": _fake_evidence()}
        _run_dimensions(config)
    incr.assert_not_called()
    per.assert_called_once()


def test_incremental_mode_uses_incremental_loop() -> None:
    """Baseline: --incremental path remains unchanged."""
    config = _minimal_config(diff_from=None, skip_scoring=False, incremental=True)
    with patch("quodeq.analysis._pipeline.run_incremental_loop") as incr, \
         patch("quodeq.analysis._pipeline.run_per_dimension_loop") as per, \
         patch("quodeq.analysis._pipeline.load_analysis_context") as ctx:
        ctx.return_value = (["security"], type("C", (), {"total": 1})())
        incr.return_value = {"security": _fake_evidence()}
        _run_dimensions(config)
    incr.assert_called_once()
    per.assert_not_called()


def test_save_dimension_fingerprint_is_noop_when_skip_scoring(tmp_path: Path) -> None:
    """The underlying save_dimension_fingerprint must short-circuit in diff mode.

    Gating here (not at call sites) covers all callers: _process_single_dimension,
    _run_dry_run, etc.
    """
    from quodeq.analysis._incremental_evidence import save_dimension_fingerprint

    config = _minimal_config(diff_from="main", skip_scoring=True)
    config.work_dir = tmp_path
    # With skip_scoring True, no fingerprint file should be written.
    save_dimension_fingerprint(config, "security")
    assert not list(tmp_path.glob("*_fingerprint.json"))


def test_save_dimension_fingerprint_writes_when_not_skip_scoring(tmp_path: Path) -> None:
    """Baseline: normal mode must still write the fingerprint."""
    from quodeq.analysis._incremental_evidence import save_dimension_fingerprint

    config = _minimal_config(diff_from=None, skip_scoring=False)
    config.work_dir = tmp_path
    # Patch the underlying save_fingerprint so we don't exercise the full
    # fingerprint-build path (which requires source files on disk).
    with patch("quodeq.analysis._incremental_evidence.save_fingerprint") as real_save:
        save_dimension_fingerprint(config, "security", files=[], analyzed_files=set())
    real_save.assert_called_once()
