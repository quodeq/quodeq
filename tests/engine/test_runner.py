"""Tests for runner (full pipeline orchestration)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis.manifest import AnalysisTarget, SourceManifest
from quodeq.engine.scoring_pipeline import run_full
from quodeq.analysis.runner import run, RunConfig, EvaluationError
from quodeq.analysis._types import AnalysisOptions
from quodeq.core.evidence.merge import merge_evidence
from quodeq.core.evidence.model import Evidence, PrincipleEvidence
from tests.engine.conftest import _evidence_line


def _make_universal_config(base: Path) -> dict:
    """Create minimal universal config files (detection.json + dimensions.json) in a temp dir.

    Returns the parsed dimensions data.
    """
    config_dir = base / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    (config_dir / "detection.json").write_text(json.dumps({
        "extensions": {".ts": "typescript", ".tsx": "typescript"},
        "config_files": {"tsconfig.json": "typescript"},
        "skip_dirs": ["node_modules", ".git"],
    }))

    dims_data = {"applies": [{"id": "security", "weight": 1.2}]}
    (config_dir / "dimensions.json").write_text(json.dumps(dims_data))
    return dims_data


def _manifest(total_files: int = 0) -> SourceManifest:
    target = AnalysisTarget(name="typescript", language="typescript", total_files=total_files)
    return SourceManifest(targets=[target], total_files=total_files)


def _stream_event_with_evidence(*evidence_lines: str) -> str:
    """Build a stream-json file content with assistant text events."""
    events = []
    for line in evidence_lines:
        events.append(json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": line}]},
        }))
    return "\n".join(events) + "\n"


def _mock_run_analysis_factory(stream_content: str):
    """Return a mock run_analysis that writes stream_content to the stream file."""
    def mock_run_analysis(work_dir, prompt, stream_file, **kwargs):
        Path(stream_file).write_text(stream_content)
    return mock_run_analysis


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------

class TestRun:
    @patch("quodeq.analysis._dimension_steps.run_analysis")
    def test_end_to_end_with_mock(self, mock_analysis, tmp_path):
        dims_data = _make_universal_config(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.ts").write_text("const x = eval(input);\n")

        stream_content = _stream_event_with_evidence(
            _evidence_line(p="ts-001", t="violation"),
            _evidence_line(p="ts-001", t="compliance", file="src/safe.ts"),
        )
        mock_analysis.side_effect = _mock_run_analysis_factory(stream_content)

        config = RunConfig(
            src=src,
            language="typescript",
            work_dir=tmp_path,
            manifest=_manifest(2),
            dimensions_data=dims_data,
            # Incremental orchestrator short-circuits to None for manifests with source_files,
            # so use clean-scan path to exercise the full runner pipeline.
            options=AnalysisOptions(incremental=False),
        )
        evidence = run(config)

        assert evidence.language == "typescript"
        assert "ts-001" in evidence.principles
        pe = evidence.principles["ts-001"]
        assert len(pe.violations) == 1
        assert len(pe.compliance) == 1
        assert pe.metrics["is_balanced"] is True

    @patch("quodeq.analysis._dimension_steps.run_analysis")
    def test_empty_project(self, mock_analysis, tmp_path):
        dims_data = _make_universal_config(tmp_path)
        src = tmp_path / "src"
        src.mkdir()

        # Empty stream — no evidence
        mock_analysis.side_effect = _mock_run_analysis_factory("")

        config = RunConfig(
            src=src,
            language="typescript",
            work_dir=tmp_path,
            dimensions_data=dims_data,
        )
        evidence = run(config)
        assert evidence.principles == {}
        assert evidence.coverage_pct == 0.0

    @patch("quodeq.analysis._dimension_steps.run_analysis")
    def test_invalid_stream_skipped(self, mock_analysis, tmp_path):
        dims_data = _make_universal_config(tmp_path)
        src = tmp_path / "src"
        src.mkdir()

        # Stream with error event
        error_stream = json.dumps({"type": "result", "is_error": True, "result": "API error"}) + "\n"
        mock_analysis.side_effect = _mock_run_analysis_factory(error_stream)

        config = RunConfig(
            src=src,
            language="typescript",
            work_dir=tmp_path,
            manifest=_manifest(1),
            dimensions_data=dims_data,
        )
        evidence = run(config)
        assert evidence.principles == {}

    @patch("quodeq.analysis._dimension_steps.run_analysis")
    def test_zero_findings_raises_error(self, mock_analysis, tmp_path):
        """An evaluation with source files but 0 findings is broken, not successful."""
        dims_data = _make_universal_config(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.ts").write_text("const x = 1;\n")

        # Valid stream with no evidence lines — simulates tools being blocked
        empty_stream = json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "I could not read any files."}]},
        }) + "\n" + json.dumps({"type": "result", "result": "done"}) + "\n"
        mock_analysis.side_effect = _mock_run_analysis_factory(empty_stream)

        config = RunConfig(
            src=src,
            language="typescript",
            work_dir=tmp_path,
            manifest=_manifest(5),
            dimensions_data=dims_data,
            # Incremental orchestrator short-circuits to None for manifests with source_files,
            # so use clean-scan path to exercise the full runner pipeline.
            options=AnalysisOptions(incremental=False),
        )
        with pytest.raises(EvaluationError, match="0 findings"):
            run(config)

    @patch("quodeq.analysis._dimension_steps.run_analysis")
    def test_stream_files_created(self, mock_analysis, tmp_path):
        dims_data = _make_universal_config(tmp_path)
        src = tmp_path / "src"
        src.mkdir()

        mock_analysis.side_effect = _mock_run_analysis_factory(
            _stream_event_with_evidence(_evidence_line())
        )

        config = RunConfig(
            src=src,
            language="typescript",
            work_dir=tmp_path,
            manifest=_manifest(1),
            dimensions_data=dims_data,
            # Incremental orchestrator short-circuits to None for manifests with source_files,
            # so use clean-scan path to exercise the full runner pipeline.
            options=AnalysisOptions(incremental=False),
        )
        run(config)

        assert (tmp_path / "security_live.stream").exists()
        assert (tmp_path / "security_evidence.jsonl").exists()


# ---------------------------------------------------------------------------
# merge_evidence
# ---------------------------------------------------------------------------

class TestMergeEvidence:
    def test_merge_empty(self, tmp_path):
        merged = merge_evidence([], source_file_count=0, src=str(tmp_path), language="ts")
        assert merged.principles == {}
        assert merged.files_read == 0

    def test_merge_single(self, tmp_path):
        pe = PrincipleEvidence(
            practice_id="ts-001", display_name="Avoid eval()",
            dimension="security", severity="high",
            violations=[{"file": "a.ts"}], compliance=[],
        )
        pe.compute_metrics()
        ev = Evidence(
            repository="test", language="ts", date="2026-03-06",
            source_file_count=10, files_read=5, coverage_pct=50.0,
            principles={"ts-001": pe},
        )
        merged = merge_evidence([ev], source_file_count=10, src=str(tmp_path), language="ts")
        assert "ts-001" in merged.principles
        assert merged.files_read == 5

    def test_merge_multiple_dimensions(self, tmp_path):
        pe1 = PrincipleEvidence(
            practice_id="ts-001", display_name="Avoid eval()",
            dimension="security", severity="high",
            violations=[{"file": "a.ts"}], compliance=[],
        )
        pe1.compute_metrics()
        pe2 = PrincipleEvidence(
            practice_id="ts-002", display_name="Small functions",
            dimension="maintainability", severity="medium",
            violations=[], compliance=[{"file": "b.ts"}],
        )
        pe2.compute_metrics()

        ev1 = Evidence(
            repository="test", language="ts", date="2026-03-06",
            source_file_count=10, files_read=5, coverage_pct=50.0,
            principles={"ts-001": pe1},
        )
        ev2 = Evidence(
            repository="test", language="ts", date="2026-03-06",
            source_file_count=10, files_read=8, coverage_pct=80.0,
            principles={"ts-002": pe2},
        )

        merged = merge_evidence([ev1, ev2], source_file_count=10, src=str(tmp_path), language="ts")
        assert "ts-001" in merged.principles
        assert "ts-002" in merged.principles
        assert merged.files_read == 8  # max

    def test_merge_overlapping_practices(self, tmp_path):
        pe1 = PrincipleEvidence(
            practice_id="ts-001", display_name="Avoid eval()",
            dimension="security", severity="high",
            violations=[{"file": "a.ts"}], compliance=[],
        )
        pe1.compute_metrics()
        pe2 = PrincipleEvidence(
            practice_id="ts-001", display_name="Avoid eval()",
            dimension="security", severity="high",
            violations=[{"file": "b.ts"}], compliance=[{"file": "c.ts"}],
        )
        pe2.compute_metrics()

        ev1 = Evidence(
            repository="test", language="ts", date="2026-03-06",
            source_file_count=10, files_read=3, coverage_pct=30.0,
            principles={"ts-001": pe1},
        )
        ev2 = Evidence(
            repository="test", language="ts", date="2026-03-06",
            source_file_count=10, files_read=5, coverage_pct=50.0,
            principles={"ts-001": pe2},
        )

        merged = merge_evidence([ev1, ev2], source_file_count=10, src=str(tmp_path), language="ts")
        pe = merged.principles["ts-001"]
        assert len(pe.violations) == 2
        assert len(pe.compliance) == 1
        assert pe.metrics["is_balanced"] is True
