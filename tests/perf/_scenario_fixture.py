"""Seeding and metrics for the wider budget scenarios (fleet, asOf, poll, spawn).

Builds on ``_budget_fixture``: the same project shape, repeated for a fleet,
plus one run that is still in flight, and two coarser metrics next to the
read counts: response bytes and ``tracemalloc`` peak.
"""
from __future__ import annotations

import json
import os
import tracemalloc
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from quodeq.core.run.state import RunState, RunStatus
from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.data.events.writer import EventLogWriter
from quodeq.data.fs.run_status_store import write_status
from quodeq.services import scan_progress
from tests.perf._budget_fixture import PROJECT, _violation, seed_project

FLEET = [f"fleet-{n:02d}" for n in range(10)]
RUNNING_RUN = "20260201T000000"
RUNNING_JOB = f"ext-{RUNNING_RUN}"
RUNNING_DIMENSIONS = ["security", "maintainability"]
# The in-flight run has scored security and is still on maintainability.
_RUNNING_VIOLATIONS = 4
# A day inside the seeded history, so the asOf lookup lands between runs.
AS_OF = "2026-01-03T12:00:00Z"
# Progress reports elapsed seconds since started_at; pin "now" so the float's
# width, and with it the response size, does not drift with the wall clock.
_NOW = datetime(2026, 2, 1, 0, 10, tzinfo=timezone.utc)

# tracemalloc peaks move a little with allocator state and interpreter
# version, so they are held to a band rather than an exact value.
PEAK_HEADROOM = 0.2
_KIB = 1024


def seed_fleet(reports_root: Path) -> None:
    """Seed one full project per FLEET name, each with the single-project shape."""
    for name in FLEET:
        seed_project(reports_root, name)


def seed_running_run(reports_root: Path) -> Path:
    """Add an in-flight run to PROJECT: running status, live pid, no scan.json.

    Security has its report and events; maintainability has neither, so the
    poll endpoints see a run that is genuinely half way.
    """
    run_dir = reports_root / PROJECT / RUNNING_RUN
    (run_dir / "evaluation").mkdir(parents=True)
    (run_dir / "evidence").mkdir()
    (run_dir / "evidence" / "manifest.json").write_text('{"language_stats": {}}', encoding="utf-8")
    violations = [_violation(i) for i in range(_RUNNING_VIOLATIONS)]
    (run_dir / "evaluation" / "security.json").write_text(json.dumps({
        "dimension": "security", "overallScore": "6.0/10", "overallGrade": "Adequate",
        "principles": [], "compliance": [],
        "violations": [{"principle": v["practice_id"], "req": v["req"], "file": v["file"],
                        "line": v["line"], "severity": v["severity"], "snippet": v["snippet"]}
                       for v in violations],
        "totals": {"violationCount": len(violations), "complianceCount": 0,
                   "severity": {"critical": 0, "major": len(violations), "minor": 0}},
    }), encoding="utf-8")
    writer = EventLogWriter(run_dir / "events.jsonl")
    for v in violations:
        writer.emit(JudgmentCreatedEvent(payload=JudgmentPayload(**v)))
    (run_dir / ".pid").write_text(str(os.getpid()), encoding="utf-8")
    write_status(run_dir, RunStatus(
        state=RunState.RUNNING, job_id=RUNNING_JOB, started_at="2026-02-01T00:00:00+00:00",
        dimensions=RUNNING_DIMENSIONS, phase="evaluating", current_dimension="maintainability",
        pid=os.getpid(),
    ))
    return run_dir


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return _NOW if tz is None else _NOW.astimezone(tz)


def freeze_progress_clock(monkeypatch) -> None:
    """Make the progress route's elapsed-time reading deterministic."""
    monkeypatch.setattr(scan_progress, "datetime", _FrozenDatetime)


def get_ok(client, url: str) -> int:
    """GET *url*, assert 200, return the body size in bytes."""
    response = client.get(url)
    assert response.status_code == 200, (url, response.status_code, response.get_data(as_text=True)[:200])
    return len(response.get_data())


@contextmanager
def peak_kib():
    """Yield a dict that receives the block's tracemalloc peak in KiB under ``peak_kib``."""
    out: dict[str, int] = {}
    tracemalloc.start()
    try:
        yield out
    finally:
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        out["peak_kib"] = peak // _KIB


def check_budgets(measured: dict[str, dict[str, int]], budgets: dict[str, dict[str, int]]) -> None:
    """Exact match for counts and bytes; a PEAK_HEADROOM band for ``peak_kib``.

    The band is one-sided: a lower peak never fails, so the memory metric
    stays coarse and only a real growth trips it. Scenarios without a
    ``peak_kib`` are not checked for memory.
    """
    over = {
        f"{scenario}.{kind}": (value, budgets.get(scenario, {}).get(kind, 0))
        for scenario, metrics in measured.items() for kind, value in metrics.items()
        if kind != "peak_kib" and value > budgets.get(scenario, {}).get(kind, 0)
    }
    assert not over, f"over budget (measured, budget): {over}"
    exact_measured = {s: {k: v for k, v in m.items() if k != "peak_kib"} for s, m in measured.items()}
    exact_budgets = {s: {k: v for k, v in m.items() if k != "peak_kib"} for s, m in budgets.items()}
    assert exact_measured == exact_budgets, (
        "dropped below budget; lock the improvement in with "
        "QUODEQ_UPDATE_BUDGETS=1 uv run pytest tests/perf and commit the budgets file"
    )
    peaks_over = {
        scenario: (metrics["peak_kib"], budgets[scenario]["peak_kib"])
        for scenario, metrics in measured.items()
        if "peak_kib" in metrics and metrics["peak_kib"] > budgets[scenario]["peak_kib"] * (1 + PEAK_HEADROOM)
    }
    assert not peaks_over, f"tracemalloc peak over budget by more than {PEAK_HEADROOM:.0%} (measured, budget): {peaks_over}"

