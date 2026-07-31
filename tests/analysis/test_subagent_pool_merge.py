"""Tests for SubagentPool.merge_jsonl — JSONL merging and deduplication."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.analysis.subagents.pool import SubagentPool, SubagentResult


class TestMergeJsonl:
    def _make_result(self, tmp_path: Path, agent_id: str, findings: list[dict]) -> SubagentResult:
        jsonl = tmp_path / f"{agent_id}.jsonl"
        with open(jsonl, "w") as f:
            for finding in findings:
                f.write(json.dumps(finding) + "\n")
        return SubagentResult(
            agent_id=agent_id, jsonl_file=jsonl,
            stream_file=tmp_path / f"{agent_id}.stream", success=True,
        )

    def test_merges_unique_findings(self, tmp_path: Path) -> None:
        r1 = self._make_result(tmp_path, "a0", [
            {"p": "P1", "t": "violation", "file": "a.py", "line": 1},
            {"p": "P2", "t": "compliance", "file": "b.py", "line": 2},
        ])
        r2 = self._make_result(tmp_path, "a1", [
            {"p": "P3", "t": "violation", "file": "c.py", "line": 3},
        ])

        output = tmp_path / "merged.jsonl"
        SubagentPool.merge_jsonl([r1, r2], output)

        lines = output.read_text().strip().splitlines()
        assert len(lines) == 3

    def test_deduplicates_across_agents(self, tmp_path: Path) -> None:
        finding = {"p": "P1", "t": "violation", "file": "a.py", "line": 10}
        r1 = self._make_result(tmp_path, "a0", [finding])
        r2 = self._make_result(tmp_path, "a1", [finding])

        output = tmp_path / "merged.jsonl"
        SubagentPool.merge_jsonl([r1, r2], output)

        lines = output.read_text().strip().splitlines()
        assert len(lines) == 1

    def test_skips_missing_jsonl(self, tmp_path: Path) -> None:
        r = SubagentResult(
            agent_id="a0",
            jsonl_file=tmp_path / "nonexistent.jsonl",
            stream_file=tmp_path / "a0.stream",
            success=False,
        )
        output = tmp_path / "merged.jsonl"
        SubagentPool.merge_jsonl([r], output)
        assert output.read_text() == ""

    def test_empty_results_produce_empty_file(self, tmp_path: Path) -> None:
        output = tmp_path / "merged.jsonl"
        SubagentPool.merge_jsonl([], output)
        assert output.read_text() == ""

    def test_malformed_lines_skipped(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "bad.jsonl"
        jsonl.write_text("not json\n" + json.dumps({"p": "P1", "t": "violation", "file": "a.py", "line": 1}) + "\n")
        r = SubagentResult(agent_id="a0", jsonl_file=jsonl, stream_file=tmp_path / "a0.stream", success=True)

        output = tmp_path / "merged.jsonl"
        SubagentPool.merge_jsonl([r], output)

        lines = output.read_text().strip().splitlines()
        assert len(lines) == 1
