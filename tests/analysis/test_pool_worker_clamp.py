"""Tests for per-agent max_duration clamping to remaining run budget."""
import time
from pathlib import Path

from quodeq.analysis._config import AnalysisConfig
from quodeq.analysis.subagents._pool_worker import build_agent_config, WorkerContext


def _wctx(tmp_path: Path) -> WorkerContext:
    return WorkerContext(
        dimension="reliability",
        dimension_key="reliability",
        evidence_dir=tmp_path,
        queue_path=tmp_path / "queue.json",
    )


def test_agent_max_duration_clamped_to_remaining_budget(tmp_path):
    now = time.monotonic()
    base = AnalysisConfig(
        jsonl_file=tmp_path / "x.jsonl",
        ai_cmd="claude",
        ai_model="claude-opus-4-7",
        max_duration=600,         # 10 min per-agent baseline
        pool_budget=600,          # 10 min total budget (legacy field, still used)
        deadline_at=now + 90,     # only 90s left until deadline
    )
    ac, _, _ = build_agent_config(0, base, _wctx(tmp_path))
    # Agent must die at the deadline, not 10 minutes from now.
    assert ac.max_duration is not None
    assert ac.max_duration <= 90
    assert ac.max_duration >= 80   # allow small slack for monotonic-clock jitter


def test_agent_max_duration_unclamped_when_no_deadline(tmp_path):
    base = AnalysisConfig(
        jsonl_file=tmp_path / "x.jsonl",
        ai_cmd="claude",
        ai_model="claude-opus-4-7",
        max_duration=600,
        pool_budget=0,            # unlimited
        deadline_at=None,
    )
    ac, _, _ = build_agent_config(0, base, _wctx(tmp_path))
    assert ac.max_duration == 600
