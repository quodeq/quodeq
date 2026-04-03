"""Integration tests for consolidated multi-dimension evaluation."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from quodeq.analysis.subprocess import AnalysisConfig
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.subagents.runner import process_consolidated_dimensions
from quodeq.analysis.runner import AnalysisOptions, RunConfig
from quodeq.analysis.manifest import SourceManifest, AnalysisTarget


def _write_compiled_standards(tmp_path):
    """Create minimal compiled standards for security and maintainability."""
    compiled = tmp_path / "standards" / "compiled"
    compiled.mkdir(parents=True)
    for dim, req_id, principle in [
        ("security", "S-CON-1", "Confidentiality"),
        ("maintainability", "M-MOD-1", "Modularity"),
    ]:
        data = {
            "id": dim,
            "principles": [{
                "name": principle,
                "source": "iso25010",
                "requirements": [{
                    "id": req_id,
                    "source": "iso25010",
                    "text": f"Test requirement for {dim}",
                    "refs": [],
                }],
            }],
        }
        (compiled / f"{dim}.json").write_text(json.dumps(data))
    return tmp_path / "standards"


def _consolidated_run_analysis(work_dir, prompt, stream_file, config):
    """Mock run_analysis that writes multi-dimension findings and drains queue."""
    stream_file.parent.mkdir(parents=True, exist_ok=True)
    stream_file.write_text("")
    # Drain queue
    if config.queue_path:
        from quodeq.analysis.subagents.file_queue import FileQueue
        queue = FileQueue(config.queue_path)
        queue.take(queue.remaining(), agent_id=config.agent_id)
    # Write findings from both dimensions
    if config.jsonl_file:
        with open(config.jsonl_file, "a") as f:
            f.write(json.dumps({
                "schema_version": 1, "p": "Confidentiality", "d": "security",
                "t": "violation", "req": "S-CON-1", "file": "a.py", "line": 1,
                "w": "hardcoded secret", "severity": "critical", "snippet": "KEY='abc'",
            }) + "\n")
            f.write(json.dumps({
                "schema_version": 1, "p": "Modularity", "d": "maintainability",
                "t": "violation", "req": "M-MOD-1", "file": "b.py", "line": 10,
                "w": "high complexity", "severity": "major", "snippet": "def big():...",
            }) + "\n")
            f.write(json.dumps({
                "schema_version": 1, "p": "Confidentiality", "d": "security",
                "t": "compliance", "req": "S-CON-1", "file": "c.py", "line": 5,
                "w": "secrets properly loaded", "severity": "major", "snippet": "os.environ['KEY']",
            }) + "\n")


def _make_consolidated_config(tmp_path):
    """Build a RunConfig and context for consolidated multi-dimension tests."""
    standards_dir = _write_compiled_standards(tmp_path)
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    for i in range(10):
        (work_dir / f"file{i}.py").write_text(f"# file {i}")

    target = AnalysisTarget(
        name="python", language="python",
        source_files=[f"file{i}.py" for i in range(10)], total_files=10,
    )
    manifest = SourceManifest(targets=[target], total_files=10)
    config = RunConfig(
        src=work_dir, language="python", standards_dir=standards_dir,
        work_dir=work_dir,
        options=AnalysisOptions(max_subagents=5, consolidated=True),
        manifest=manifest, target=target,
        dimensions_data={
            "applies": [
                {"id": "security", "weight": 1.0},
                {"id": "maintainability", "weight": 1.0},
            ],
        },
    )
    ctx = SimpleNamespace(
        dimensions_data=config.dimensions_data,
        date_str="2026-03-22", template="", subagent_template="", total=2,
    )
    return config, ctx


class TestConsolidatedIntegration:
    def test_consolidated_produces_per_dimension_evidence(self, tmp_path):
        """Consolidated mode splits findings by dimension correctly."""
        config, ctx = _make_consolidated_config(tmp_path)

        with patch("quodeq.analysis.subagents._pool_worker.run_analysis", _consolidated_run_analysis):
            result = process_consolidated_dimensions(config, ["security", "maintainability"], ctx)

        assert "security" in result
        assert "maintainability" in result

        sec = result["security"]
        sec_v = sum(len(pe.violations) for pe in sec.principles.values())
        sec_c = sum(len(pe.compliance) for pe in sec.principles.values())
        assert sec_v == 1
        assert sec_c == 1

        maint = result["maintainability"]
        maint_v = sum(len(pe.violations) for pe in maint.principles.values())
        assert maint_v == 1
