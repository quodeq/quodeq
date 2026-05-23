"""End-to-end: pool.exit_reason flows into the Evidence built by _collect_evidence."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from quodeq.analysis.subagents._evidence_collector import _CollectionContext, _collect_evidence


def test_collect_evidence_passes_exit_reason_into_evidence(tmp_path):
    config = MagicMock()
    config.standards_dir = None
    config.evaluators_dir = None
    config.language = "python"
    config.src = tmp_path
    config.source_file_count = 100
    config.target = None

    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    (evidence_dir / "security_evidence.jsonl").write_text("", encoding="utf-8")

    ctx_obj = MagicMock()
    ctx_obj.date_str = "2026-05-23"

    collection = _CollectionContext(results=[], ctx=ctx_obj, files=[], exit_reason="time_limit")

    with patch("quodeq.analysis.subagents._evidence_collector.SubagentPool.deduplicate_jsonl"), \
         patch("quodeq.analysis.subagents._evidence_collector._collect_all_evidence", return_value=5):
        ev = _collect_evidence(config, "security", evidence_dir, collection)

    assert ev.exit_reason == "time_limit"
