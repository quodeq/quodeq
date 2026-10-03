"""build_api_batch_context's overrides_loader seam: injecting a fake
standards-overrides loader instead of the concrete data-layer one."""
from __future__ import annotations

from unittest.mock import patch

from quodeq.analysis.subprocess import AnalysisConfig, build_api_batch_context


def test_uses_injected_overrides_loader_instead_of_the_data_layer_default(tmp_path):
    """overrides_loader is a call-time seam: when set, build_api_batch_context
    must resolve standards overrides through it instead of calling the
    concrete load_project_overrides. The lazy import means the concrete
    loader is never even imported in this path, so the proof is what
    reaches load_standards_text."""
    real_file = tmp_path / "real.py"
    real_file.write_text("print(1)\n")

    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    jsonl_file = evidence_dir / "security_evidence.jsonl"
    stream_file = evidence_dir / "agent.stream"
    cfg = AnalysisConfig(jsonl_file=jsonl_file)

    calls: list = []
    sentinel_overrides = {"S-CON-1": {"floorMajor": 9.0}}

    def _fake_loader(work_dir):
        calls.append(work_dir)
        return sentinel_overrides

    with patch(
        "quodeq.analysis._api_batch.load_standards_text", return_value="",
    ) as spy_load_text:
        ctx = build_api_batch_context(
            tmp_path, cfg, {}, stream_file, overrides_loader=_fake_loader,
        )

    assert calls == [tmp_path]
    assert spy_load_text.call_args.kwargs["overrides"] is sentinel_overrides
    assert ctx is not None
