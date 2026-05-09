"""Performance microbenchmark for the marker-aware grouping function.

Catches O(n^2) regressions in `_group_findings_by_file`. The 500ms budget
is loose to avoid CI flakes; the point is order-of-magnitude correctness,
not micro-optimisation.
"""
from __future__ import annotations
import json
import time
from pathlib import Path

from quodeq.analysis.cache.dimension_helpers import _group_findings_by_file


def test_grouping_overhead_under_budget(tmp_path: Path):
    lines = []
    for i in range(10_000):
        lines.append({
            "file": f"src/f{i % 1000}.py", "req": "X-1", "t": "violation",
            "line": i, "severity": "minor", "w": "w", "reason": "r",
        })
    for i in range(1_000):
        lines.append({"_marker": "file_done", "file": f"src/f{i}.py", "status": "ok"})
    jsonl = tmp_path / "evidence.jsonl"
    jsonl.write_text("".join(json.dumps(line) + "\n" for line in lines))

    t0 = time.perf_counter()
    grouped, ok_files = _group_findings_by_file(jsonl)
    elapsed = time.perf_counter() - t0
    assert len(ok_files) == 1000
    assert sum(len(v) for v in grouped.values()) == 10_000
    assert elapsed < 0.5, f"grouping took {elapsed*1000:.0f}ms (budget 500ms)"
