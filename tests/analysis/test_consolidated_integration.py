"""Integration tests for consolidated multi-dimension evaluation."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from quodeq.analysis.subprocess import AnalysisConfig
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.subagents.runner import process_consolidated_dimensions
from quodeq.analysis.runner import AnalysisOptions, RunConfig
from quodeq.analysis.manifest import SourceManifest, AnalysisTarget

# See test_adaptive_scaling_integration.py for the Windows skip rationale.
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="SubagentPool FileQueue lock path needs Windows-specific work",
)

_TEST_DIM_SECURITY = "security"
_TEST_DIM_MAINTAINABILITY = "maintainability"
_TEST_REQ_SECURITY = "S-CON-1"
_TEST_REQ_MAINTAINABILITY = "M-MOD-1"
_TEST_PRINCIPLE_SECURITY = "Confidentiality"
_TEST_PRINCIPLE_MAINTAINABILITY = "Modularity"


def _write_compiled_standards(tmp_path):
    """Create minimal compiled standards for security and maintainability."""
    compiled = tmp_path / "standards" / "compiled"
    compiled.mkdir(parents=True)
    for dim, req_id, principle in [
        (_TEST_DIM_SECURITY, _TEST_REQ_SECURITY, _TEST_PRINCIPLE_SECURITY),
        (_TEST_DIM_MAINTAINABILITY, _TEST_REQ_MAINTAINABILITY, _TEST_PRINCIPLE_MAINTAINABILITY),
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
                "schema_version": 1, "p": _TEST_PRINCIPLE_SECURITY, "d": _TEST_DIM_SECURITY,
                "t": "violation", "req": _TEST_REQ_SECURITY, "file": "a.py", "line": 1,
                "w": "hardcoded secret", "severity": "critical", "snippet": "KEY='abc'",
            }) + "\n")
            f.write(json.dumps({
                "schema_version": 1, "p": _TEST_PRINCIPLE_MAINTAINABILITY, "d": _TEST_DIM_MAINTAINABILITY,
                "t": "violation", "req": _TEST_REQ_MAINTAINABILITY, "file": "b.py", "line": 10,
                "w": "high complexity", "severity": "major", "snippet": "def big():...",
            }) + "\n")
            f.write(json.dumps({
                "schema_version": 1, "p": _TEST_PRINCIPLE_SECURITY, "d": _TEST_DIM_SECURITY,
                "t": "compliance", "req": _TEST_REQ_SECURITY, "file": "c.py", "line": 5,
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
                {"id": _TEST_DIM_SECURITY, "weight": 1.0},
                {"id": _TEST_DIM_MAINTAINABILITY, "weight": 1.0},
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
            result = process_consolidated_dimensions(config, [_TEST_DIM_SECURITY, _TEST_DIM_MAINTAINABILITY], ctx)

        assert _TEST_DIM_SECURITY in result
        assert _TEST_DIM_MAINTAINABILITY in result

        sec = result[_TEST_DIM_SECURITY]
        sec_v = sum(len(pe.violations) for pe in sec.principles.values())
        sec_c = sum(len(pe.compliance) for pe in sec.principles.values())
        assert sec_v == 1
        assert sec_c == 1

        maint = result[_TEST_DIM_MAINTAINABILITY]
        maint_v = sum(len(pe.violations) for pe in maint.principles.values())
        assert maint_v == 1
