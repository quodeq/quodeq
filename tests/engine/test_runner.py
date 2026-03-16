"""Tests for runner (full pipeline orchestration)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.engine._runner_report import run_full
from quodeq.engine.runner import run, RunConfig, EvaluationError
from quodeq.engine._merge import merge_evidence
from quodeq.engine.evidence import Evidence, PrincipleEvidence
from tests.engine.conftest import _evidence_line


def _make_plugin_dir(base: Path) -> Path:
    """Create a minimal valid typescript plugin in a temp dir."""
    plugin_dir = base / "evaluators" / "typescript"
    plugin_dir.mkdir(parents=True)

    (plugin_dir / "plugin.json").write_text(json.dumps({
        "id": "typescript",
        "name": "TypeScript",
        "version": "1.0.0",
        "engine_version": "==0.5.0",
        "detects": {"extensions": [".ts"]},
    }))

    (plugin_dir / "dimensions.json").write_text(json.dumps({
        "applies": [{"id": "security", "weight": 1.2}],
    }))

    knowledge = plugin_dir / "knowledge"
    knowledge.mkdir()
    (knowledge / "analysis.md").write_text("# Analysis\nLook for eval().\n")

    return base / "evaluators"


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
    def test_unknown_plugin_error(self, tmp_path):
        evaluators_dir = tmp_path / "evaluators"
        evaluators_dir.mkdir()
        config = RunConfig(
            src=tmp_path / "src",
            plugin_id="nonexistent",
            evaluators_dir=evaluators_dir,
        )
        with pytest.raises(ValueError, match="not found"):
            run(config)

    @patch("quodeq.analysis.runner.run_analysis")
    def test_end_to_end_with_mock(self, mock_analysis, tmp_path):
        evaluators_dir = _make_plugin_dir(tmp_path)
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
            plugin_id="typescript",
            evaluators_dir=evaluators_dir,
            source_file_count=2,
            work_dir=tmp_path,
        )
        evidence = run(config)

        assert evidence.plugin_id == "typescript"
        assert "ts-001" in evidence.principles
        pe = evidence.principles["ts-001"]
        assert len(pe.violations) == 1
        assert len(pe.compliance) == 1
        assert pe.metrics["is_balanced"] is True

    @patch("quodeq.analysis.runner.run_analysis")
    def test_empty_project(self, mock_analysis, tmp_path):
        evaluators_dir = _make_plugin_dir(tmp_path)
        src = tmp_path / "src"
        src.mkdir()

        # Empty stream — no evidence
        mock_analysis.side_effect = _mock_run_analysis_factory("")

        config = RunConfig(
            src=src,
            plugin_id="typescript",
            evaluators_dir=evaluators_dir,
            source_file_count=0,
            work_dir=tmp_path,
        )
        evidence = run(config)
        assert evidence.principles == {}
        assert evidence.coverage_pct == 0.0

    @patch("quodeq.analysis.runner.run_analysis")
    def test_invalid_stream_skipped(self, mock_analysis, tmp_path):
        evaluators_dir = _make_plugin_dir(tmp_path)
        src = tmp_path / "src"
        src.mkdir()

        # Stream with error event
        error_stream = json.dumps({"type": "result", "is_error": True, "result": "API error"}) + "\n"
        mock_analysis.side_effect = _mock_run_analysis_factory(error_stream)

        config = RunConfig(
            src=src,
            plugin_id="typescript",
            evaluators_dir=evaluators_dir,
            source_file_count=1,
            work_dir=tmp_path,
        )
        evidence = run(config)
        assert evidence.principles == {}

    @patch("quodeq.analysis.runner.run_analysis")
    def test_zero_findings_raises_error(self, mock_analysis, tmp_path):
        """An evaluation with source files but 0 findings is broken, not successful."""
        evaluators_dir = _make_plugin_dir(tmp_path)
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
            plugin_id="typescript",
            evaluators_dir=evaluators_dir,
            source_file_count=5,
            work_dir=tmp_path,
        )
        with pytest.raises(EvaluationError, match="0 findings"):
            run(config)

    @patch("quodeq.analysis.runner.run_analysis")
    def test_stream_files_created(self, mock_analysis, tmp_path):
        evaluators_dir = _make_plugin_dir(tmp_path)
        src = tmp_path / "src"
        src.mkdir()

        mock_analysis.side_effect = _mock_run_analysis_factory(
            _stream_event_with_evidence(_evidence_line())
        )

        config = RunConfig(
            src=src,
            plugin_id="typescript",
            evaluators_dir=evaluators_dir,
            source_file_count=1,
            work_dir=tmp_path,
        )
        run(config)

        assert (tmp_path / "security_live.stream").exists()
        assert (tmp_path / "security_evidence.jsonl").exists()


# ---------------------------------------------------------------------------
# merge_evidence
# ---------------------------------------------------------------------------

class TestMergeEvidence:
    def test_merge_empty(self, tmp_path):
        config = RunConfig(src=tmp_path, plugin_id="ts", evaluators_dir=tmp_path)
        merged = merge_evidence([], config.source_file_count, str(config.src), config.plugin_id)
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
            repository="test", plugin_id="ts", date="2026-03-06",
            source_file_count=10, files_read=5, coverage_pct=50.0,
            principles={"ts-001": pe},
        )
        config = RunConfig(src=tmp_path, plugin_id="ts", evaluators_dir=tmp_path, source_file_count=10)
        merged = merge_evidence([ev], config.source_file_count, str(config.src), config.plugin_id)
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
            repository="test", plugin_id="ts", date="2026-03-06",
            source_file_count=10, files_read=5, coverage_pct=50.0,
            principles={"ts-001": pe1},
        )
        ev2 = Evidence(
            repository="test", plugin_id="ts", date="2026-03-06",
            source_file_count=10, files_read=8, coverage_pct=80.0,
            principles={"ts-002": pe2},
        )

        config = RunConfig(src=tmp_path, plugin_id="ts", evaluators_dir=tmp_path, source_file_count=10)
        merged = merge_evidence([ev1, ev2], config.source_file_count, str(config.src), config.plugin_id)
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
            repository="test", plugin_id="ts", date="2026-03-06",
            source_file_count=10, files_read=3, coverage_pct=30.0,
            principles={"ts-001": pe1},
        )
        ev2 = Evidence(
            repository="test", plugin_id="ts", date="2026-03-06",
            source_file_count=10, files_read=5, coverage_pct=50.0,
            principles={"ts-001": pe2},
        )

        config = RunConfig(src=tmp_path, plugin_id="ts", evaluators_dir=tmp_path, source_file_count=10)
        merged = merge_evidence([ev1, ev2], config.source_file_count, str(config.src), config.plugin_id)
        pe = merged.principles["ts-001"]
        assert len(pe.violations) == 2
        assert len(pe.compliance) == 1
        assert pe.metrics["is_balanced"] is True
