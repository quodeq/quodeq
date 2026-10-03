"""A project whose history exercises every scoring rule the API payloads reflect.

Built on the budget fixture's run writer. On top of the plain finished
runs it adds the cases a backend change is most likely to alter without
anyone noticing: a dismissal, a deletion, a pattern suppression rule, a
partial (failed) run, a finding carried forward from a previous run, a
finding on a requirement outside the shipped standards, and a child
project pointing at this one as its parent.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.data.events.writer import EventLogWriter
from quodeq.data.projection.projector import Projector
from quodeq.services.deleted import delete_finding
from quodeq.services.dismissed import dismiss_finding
from tests.perf._budget_fixture import _violation

PROJECT = "golden"
CHILD_PROJECT = "golden-child"
DIMENSION = "security"
RUN_IDS = [f"2026020{n}T000000" for n in range(6)]
PARTIAL_RUN_ID = RUN_IDS[3]
MIDDLE_RUN_ID = RUN_IDS[2]
LATEST_RUN_ID = RUN_IDS[-1]
CHILD_RUN_ID = "20260210T000000"
VIOLATIONS_PER_RUN = 5
RUN_STATE_DONE = "done"
RUN_STATE_FAILED = "failed"

# Rows in the latest run that the project-level rules act on, and the row
# (S-INT-2 in f9.py) marked as replayed from the previous run.
CARRIED_FORWARD_INDEX = 4
DISMISSED = {"req": "S-CON-6", "file": "f5.py", "line": 15}
DELETED = {"dimension": DIMENSION, "principle": "Confidentiality", "file": "f6.py"}
SUPPRESSION_RULE = {"req": "S-CON-8", "file": "f7.*", "reason": "golden rule"}
# A requirement that no shipped standard declares.
CUSTOM_STANDARD_VIOLATION = dict(
    practice_id="Custom Practice", verdict="violation", dimension=DIMENSION,
    file="custom.py", line=1, reason="r", req="X-CUS-1", severity="high", snippet="custom()",
)


def _principle_rows(violations: list[dict]) -> list[dict]:
    names = sorted({v["practice_id"] for v in violations})
    return [{"name": n, "score": "6.0/10", "grade": "Adequate"} for n in names]


def _report(violations: list[dict], date: str) -> dict:
    """The on-disk ``evaluation/<dim>.json`` shape the report writer produces:
    snake_case rows tagged with ``principle``."""
    rows = [{"principle": v["practice_id"], "req": v["req"], "file": v["file"], "line": v["line"],
             "severity": v["severity"], "snippet": v["snippet"], "reason": v["reason"],
             "carried_forward": v.get("carried_forward", False)}
            for v in violations]
    return {
        "schema_version": 1, "dimension": DIMENSION, "date": date, "filesRead": 10,
        "overallScore": "6.0/10", "overallGrade": "Adequate",
        "principles": _principle_rows(violations), "violations": rows, "compliance": [],
        "totals": {"violationCount": len(rows), "complianceCount": 0,
                   "severity": {"critical": 0, "major": len(rows), "minor": 0}},
    }


def _write_run(project_dir: Path, run_id: str, violations: list[dict], *, state: str) -> None:
    run_dir = project_dir / run_id
    (run_dir / "evaluation").mkdir(parents=True)
    (run_dir / "evidence").mkdir()
    (run_dir / "evidence" / "manifest.json").write_text('{"language_stats": {}}', encoding="utf-8")
    date = f"{run_id[:4]}-{run_id[4:6]}-{run_id[6:8]}T00:00:00Z"
    status = {"state": state, "started_at": date}
    if state != RUN_STATE_DONE:
        status["dimensions"] = {DIMENSION: {"state": state, "exit_reason": "provider_fatal"}}
    (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    if state == RUN_STATE_DONE:
        (run_dir / "evaluation" / f"{DIMENSION}.json").write_text(
            json.dumps(_report(violations, date)), encoding="utf-8")
    log = run_dir / "events.jsonl"
    writer = EventLogWriter(log)
    for v in violations:
        writer.emit(JudgmentCreatedEvent(payload=JudgmentPayload(**v)))
    Projector().ensure_projected(log, run_dir, project_dir=project_dir)


def _run_violations(n: int) -> list[dict]:
    return [_violation(i) for i in range(n, n + VIOLATIONS_PER_RUN)]


def _latest_violations() -> list[dict]:
    rows = _run_violations(len(RUN_IDS) - 1)
    rows[CARRIED_FORWARD_INDEX] = {**rows[CARRIED_FORWARD_INDEX], "carried_forward": True}
    return [*rows, CUSTOM_STANDARD_VIOLATION]


def _repo_info(project: str, *, parent: str | None = None) -> dict:
    info = {"uuid": project, "name": project, "discipline": "software", "location": "local",
            "path": f"/repos/{project}"}
    if parent:
        info["parent"] = parent
    return info


def seed_golden_project(reports_root: Path) -> Path:
    """Write the golden project and its child; return the project directory."""
    project_dir = reports_root / PROJECT
    project_dir.mkdir(parents=True)
    (project_dir / "repository_info.json").write_text(json.dumps(_repo_info(PROJECT)), encoding="utf-8")
    for n, run_id in enumerate(RUN_IDS):
        if run_id == PARTIAL_RUN_ID:
            _write_run(project_dir, run_id, _run_violations(n)[:2], state=RUN_STATE_FAILED)
        elif run_id == LATEST_RUN_ID:
            _write_run(project_dir, run_id, _latest_violations(), state=RUN_STATE_DONE)
        else:
            _write_run(project_dir, run_id, _run_violations(n), state=RUN_STATE_DONE)
    (project_dir / "suppression_rules.json").write_text(
        json.dumps({"version": 1, "rules": [SUPPRESSION_RULE]}), encoding="utf-8")
    dismiss_finding(project_dir, DISMISSED)
    delete_finding(project_dir, DELETED)

    child_dir = reports_root / CHILD_PROJECT
    child_dir.mkdir()
    (child_dir / "repository_info.json").write_text(
        json.dumps(_repo_info(CHILD_PROJECT, parent=PROJECT)), encoding="utf-8")
    _write_run(child_dir, CHILD_RUN_ID, _run_violations(0), state=RUN_STATE_DONE)
    return project_dir
