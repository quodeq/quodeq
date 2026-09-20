"""Performance microbenchmark for the marker-aware grouping function.

Catches O(n^2) regressions in `group_findings_by_file`. The 500ms budget
is loose to avoid CI flakes; the point is order-of-magnitude correctness,
not micro-optimisation.
"""
from __future__ import annotations
import json
import time
from pathlib import Path

from quodeq.analysis.cache.dimension_helpers import group_findings_by_file

_TOTAL_FINDINGS = 10_000
_UNIQUE_FILES = 1_000  # both the file-name modulus and the file_done marker count
_BUDGET_S = 0.5


def test_grouping_overhead_under_budget(tmp_path: Path):
    lines = []
    for i in range(_TOTAL_FINDINGS):
        lines.append({
            "file": f"src/f{i % _UNIQUE_FILES}.py", "req": "X-1", "t": "violation",
            "line": i, "severity": "minor", "w": "w", "reason": "r",
        })
    for i in range(_UNIQUE_FILES):
        lines.append({"_marker": "file_done", "file": f"src/f{i}.py", "status": "ok"})
    jsonl = tmp_path / "evidence.jsonl"
    jsonl.write_text("".join(json.dumps(line) + "\n" for line in lines))

    t0 = time.perf_counter()
    grouped, ok_files = group_findings_by_file(jsonl)
    elapsed = time.perf_counter() - t0
    assert len(ok_files) == _UNIQUE_FILES
    assert sum(len(v) for v in grouped.values()) == _TOTAL_FINDINGS
    assert elapsed < _BUDGET_S, f"grouping took {elapsed*1000:.0f}ms (budget {_BUDGET_S*1000:.0f}ms)"
