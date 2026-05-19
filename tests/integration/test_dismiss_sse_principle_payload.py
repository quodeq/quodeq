"""Regression: SSE scores.updated payload carries per-principle score+grade
in the shape the UI expects, and fires whenever per-principle state changes
— not only when the dimension's overall score changes.

The UI's `usePrincipleData` hook looks up the live principle score with:

    pgMap = new Map(dimData.principles.map(p => [p.principle, p]))
    pgMap.get(evalPrincipal.principle)

where `evalPrincipal.principle` is the principle *name* (e.g. "Adaptability")
read from `evalData.principleGrades[].principle`. The latter is produced by
`parse_eval_from_json` from the JSON file's `principles[].name` field.

Two contracts pinned here:

1. **Shape**: SSE payload's `principles[].principle` MUST equal that
   human-readable principle name — not an opaque id or slug.

2. **Liveness**: SSE `scores.updated` MUST fire when a dismiss changes
   per-principle state, even if the dimension's rolled-up score happens to
   stay the same (rounding / low-data / current-scoring-engine quirks).
   Before this regression, the fingerprint only looked at
   ``dimension_scores`` and missed principle-level changes silently.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.api._run_event_stream import WatcherState, compute_tick
from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.writer import EventLogWriter
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository
from quodeq.services.dismissed import dismiss_finding


def _seed(
    run_dir: Path, *, practice_id: str, req: str, file: str, line: int,
    dimension: str = "Maintainability", verdict: str = "violation",
    severity: str = "high",
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    EventLogWriter(run_dir / "events.jsonl").emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id=practice_id, verdict=verdict, dimension=dimension,
        file=file, line=line, reason="r", req=req, severity=severity,
    )))


def test_scores_updated_fires_on_principle_change_even_if_dimension_score_unchanged(
    tmp_path: Path,
) -> None:
    """Dismissing a finding must trigger scores.updated whenever per-principle
    state changes — not only when the dimension's overall score changes.

    With the current scoring engine, a single-principle dimension can keep the
    same overall score after one violation is dismissed (because the score
    rounds to the same bucket, or because the scorer doesn't penalise enough
    for low-data cases). The SSE fingerprint must still observe the change so
    the UI's `usePrincipleData` gets the updated principle row.
    """
    eval_dir = tmp_path / "evaluations"
    project_dir = eval_dir / "proj1"
    run_dir = project_dir / "run1"

    # Two violations + one compliance, all "Adaptability". Dismissing R1 leaves
    # the principle row alive (R2 + R3) with different finding_count.
    _seed(run_dir, practice_id="Adaptability", req="R1", file="a.py", line=10)
    _seed(run_dir, practice_id="Adaptability", req="R2", file="b.py", line=20)
    _seed(
        run_dir, practice_id="Adaptability", req="R3", file="c.py", line=30,
        verdict="compliance",
    )

    # Project so initial grade rows exist.
    SqliteFindingsRepository(run_dir).list_by_dimension("Maintainability")

    # Baseline tick — primes fingerprint with the un-dismissed state.
    state = WatcherState()
    _, state = compute_tick(run_dir, state)

    # Dismiss one finding.
    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10})

    # Force projection so finding.verdict is flipped and grades recomputed.
    SqliteFindingsRepository(run_dir).list_by_dimension("Maintainability")

    events, _ = compute_tick(run_dir, state)
    grade_events = [e for e in events if e[0] == "scores.updated"]
    assert len(grade_events) == 1, (
        "Expected scores.updated after dismiss because principle_grades changed "
        f"(finding_count 2 -> 1, dismissed_count 0 -> 1). Got events: "
        f"{[e[0] for e in events]}. This means the SSE fingerprint only watches "
        f"dimension_scores and swallowed a real per-principle change — the UI's "
        f"usePrincipleData will never see the dismiss."
    )

    payload = json.loads(grade_events[0][1])
    maint = next(
        (d for d in payload.get("dimensions", []) if d.get("dimension") == "Maintainability"),
        None,
    )
    assert maint is not None, f"Maintainability dimension missing from payload: {payload}"

    principles = maint.get("principles") or []
    assert len(principles) > 0, (
        f"payload.dimensions[].principles is empty — UI cannot look up live score. "
        f"Dimension dict: {maint}"
    )

    # Critical contract: principle field equals the human-readable name the UI
    # uses on the detail page (evalPrincipal.principle).
    principle_names = [p.get("principle") for p in principles]
    assert "Adaptability" in principle_names, (
        f"SSE payload principles[].principle = {principle_names!r}, but UI looks up "
        f"'Adaptability' (the principle name). This is the silent merge-fail that "
        f"makes the principle-detail-page grade stay stale after a dismiss."
    )
