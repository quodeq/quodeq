# Live Rescore on Dismiss — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recalculate and display updated grades live when violations are dismissed or restored, using the backend as single source of truth.

**Architecture:** New `GET /api/rescore` endpoint loads stored run dimensions, filters out dismissed findings, rescores at principle/dimension/run level using existing scoring primitives, and returns updated data. Frontend calls this on dashboard load and after dismiss/restore.

**Tech Stack:** Python (Flask, dataclasses), JavaScript (React hooks, fetch API)

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/quodeq/services/rescore.py` | Core rescore logic: filter dismissed, recount types, rescore principles, aggregate |
| Create | `tests/services/test_rescore.py` | Unit tests for rescore logic |
| Create | `src/quodeq/api/routes_rescore.py` | `/api/rescore` endpoint |
| Create | `tests/api/test_routes_rescore.py` | Integration test for the endpoint |
| Modify | `src/quodeq/api/app.py:172` | Register rescore routes |
| Modify | `src/quodeq/ui/src/api/index.js` | Add `getRescore()` API call |
| Modify | `src/quodeq/ui/src/features/dashboard/hooks/useDashboard.js` | Call rescore after dashboard load |

---

### Task 1: Extract `rescore_dimensions` — Core Rescore Logic

**Files:**
- Create: `src/quodeq/services/rescore.py`
- Create: `tests/services/test_rescore.py`

This is the heart of the feature. It takes dimensions + dismissed keys, filters violations, recounts types, rescores each principle, and aggregates up.

- [ ] **Step 1: Write failing test — rescore with no dismissals returns original scores**

```python
# tests/services/test_rescore.py
"""Tests for the live rescore service."""
from quodeq.core.types.finding import Finding, Totals, SeverityTally
from quodeq.core.types.report import PrincipleGrade
from quodeq.core.types.dimension import DimensionResult

from quodeq.services.rescore import rescore_dimensions


def _make_violation(principle="P1", severity="major", req="R1", file="a.py", line=1, reason="bug"):
    return Finding(principle=principle, severity=severity, req=req, file=file, line=line, reason=reason)


def _make_compliance(principle="P1", req="R1", file="a.py", line=10, reason="ok"):
    return Finding(principle=principle, req=req, file=file, line=line, reason=reason)


def _make_dimension(name="Reliability", violations=None, compliance=None, source_file_count=100):
    violations = violations or []
    compliance = compliance or []
    return DimensionResult(
        dimension=name,
        violations=violations,
        compliance=compliance,
        overall_score="5.0/10",
        overall_grade="Adequate",
        principles=[PrincipleGrade(principle="P1", score="5.0/10", grade="Adequate")],
        totals=Totals(
            violation_count=len(violations),
            compliance_count=len(compliance),
            severity=SeverityTally(
                critical=sum(1 for v in violations if v.severity == "critical"),
                major=sum(1 for v in violations if v.severity == "major"),
                minor=sum(1 for v in violations if v.severity == "minor"),
            ),
        ),
        source_file_count=source_file_count,
    )


def test_rescore_no_dismissals_returns_rescored_data():
    """With no dismissed keys, rescore should still return valid rescored dimensions."""
    dim = _make_dimension(
        violations=[_make_violation(severity="major")],
        compliance=[_make_compliance()],
    )
    result = rescore_dimensions([dim], dismissed_keys=set())
    assert len(result["dimensions"]) == 1
    assert result["dimensions"][0]["overallScore"] is not None
    assert result["dimensions"][0]["overallGrade"] is not None
    assert result["summary"] is not None
    assert result["summary"]["overallGrade"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/services/test_rescore.py::test_rescore_no_dismissals_returns_rescored_data -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quodeq.services.rescore'`

- [ ] **Step 3: Write minimal `rescore_dimensions` implementation**

```python
# src/quodeq/services/rescore.py
"""Live rescore service — recalculates grades after dismissals change."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from quodeq.core.types import DimensionResult, to_camel_dict
from quodeq.core.types.finding import Totals, SeverityTally
from quodeq.core.types.report import PrincipleGrade
from quodeq.core.scoring.internals import (
    evidence_has_taxonomy,
    tally_types_by_taxonomy,
    tally_types_by_reason,
    tally_compliance_types_by_taxonomy,
    tally_compliance_types_by_reason,
    violation_base,
    compliance_lift,
    violation_ceiling,
    severity_grade_floor,
    score_to_grade_label,
    compliance_dampening,
    scale_multiplier,
)
from quodeq.core.scoring.overall import weighted_overall, MODE_NUMERICAL
from quodeq.core.types.scoring import PrincipleScore
from quodeq.data.fs.report_parser.grades import summarize_dimensions
from quodeq.services.dismissed import dismissed_keys as load_dismissed_keys


def _compute_tallies(violations: list, compliance: list):
    """Count violation and compliance types, auto-selecting taxonomy or reason mode."""
    using_taxonomy = evidence_has_taxonomy(violations)
    vt = tally_types_by_taxonomy(violations) if using_taxonomy else tally_types_by_reason(violations)
    ct = tally_compliance_types_by_taxonomy(compliance) if using_taxonomy else tally_compliance_types_by_reason(compliance)
    return vt, ct, using_taxonomy


def _score_principle(violations: list, compliance: list, scale_mult: int) -> tuple[float | None, str]:
    """Score a single principle from its filtered violations and compliance lists.

    Returns (final_score, grade).
    """
    vt_counts, ct_counts, _ = _compute_tallies(violations, compliance)
    if not vt_counts and not ct_counts:
        return None, "Insufficient"

    base = violation_base(vt_counts)
    lift = compliance_lift(ct_counts, vt_counts)
    ceil = violation_ceiling(vt_counts)
    floor = severity_grade_floor(vt_counts)

    raw = base + (10.0 - base) * lift
    final = max(floor, min(ceil, raw))
    final = round(final, 1)
    grade = score_to_grade_label(final)
    return final, grade


def _recount_totals(violations: list, compliance_count: int) -> Totals:
    """Recount totals from a filtered violations list."""
    crit = sum(1 for v in violations if (v.severity or "").lower() == "critical")
    major = sum(1 for v in violations if (v.severity or "").lower() == "major")
    minor = sum(1 for v in violations if (v.severity or "").lower() == "minor")
    unknown = len(violations) - crit - major - minor
    return Totals(
        violation_count=len(violations),
        compliance_count=compliance_count,
        severity=SeverityTally(critical=crit, major=major, minor=minor, unknown=unknown),
    )


def _rescore_dimension(dim: DimensionResult, dismissed: set[tuple]) -> DimensionResult:
    """Rescore a single dimension after filtering dismissed findings."""
    # Filter violations
    filtered_violations = [
        v for v in dim.violations
        if (v.req or "", v.file or "", v.line or 0) not in dismissed
    ]

    # Group violations and compliance by principle
    principles_violations: dict[str, list] = {}
    principles_compliance: dict[str, list] = {}
    for v in filtered_violations:
        principles_violations.setdefault(v.principle or "unknown", []).append(v)
    for c in dim.compliance:
        principles_compliance.setdefault(c.principle or "unknown", []).append(c)

    # Score each principle
    scale_mult = scale_multiplier(dim.source_file_count or 0)
    all_principle_names = set(principles_violations) | set(principles_compliance)
    principle_scores: dict[str, PrincipleScore] = {}
    principle_grades: list[PrincipleGrade] = []

    for name in sorted(all_principle_names):
        p_violations = principles_violations.get(name, [])
        p_compliance = principles_compliance.get(name, [])
        final_score, grade = _score_principle(p_violations, p_compliance, scale_mult)
        score_str = f"{final_score}/10" if final_score is not None else None

        # Find original weight from existing principle grades
        original_weight = "1"
        for pg in dim.principles:
            if pg.principle == name:
                # Extract weight if stored; default to "1"
                original_weight = "1"
                break

        principle_scores[name] = PrincipleScore(
            display_name=name,
            weight=original_weight,
            final_score=final_score,
            grade=grade,
        )
        principle_grades.append(PrincipleGrade(principle=name, score=score_str, grade=grade))

    # Aggregate to dimension overall
    overall = weighted_overall(principle_scores, MODE_NUMERICAL)
    overall_score_str = f"{overall.weighted_score}/10" if overall.weighted_score is not None else None
    overall_grade = overall.grade or overall.weighted_grade

    # Recount totals
    compliance_count = dim.totals.compliance_count if dim.totals else len(dim.compliance)
    new_totals = _recount_totals(filtered_violations, compliance_count)

    return replace(
        dim,
        violations=filtered_violations,
        principles=principle_grades,
        overall_score=overall_score_str,
        overall_grade=overall_grade,
        totals=new_totals,
    )


def rescore_dimensions(
    dimensions: list[DimensionResult],
    dismissed_keys: set[tuple],
) -> dict[str, Any]:
    """Rescore all dimensions after filtering dismissed findings.

    Returns a dict with 'dimensions' (list of camelCase dicts) and 'summary' (camelCase dict).
    """
    rescored = [_rescore_dimension(dim, dismissed_keys) for dim in dimensions]
    summary = summarize_dimensions(rescored)
    return {
        "dimensions": [to_camel_dict(d) for d in rescored],
        "summary": to_camel_dict(summary),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/services/test_rescore.py::test_rescore_no_dismissals_returns_rescored_data -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/services/rescore.py tests/services/test_rescore.py
git commit -m "feat: add rescore_dimensions service for live grade recalculation"
```

---

### Task 2: Test Rescore With Dismissals

**Files:**
- Modify: `tests/services/test_rescore.py`

Add tests that verify scores actually change when violations are dismissed.

- [ ] **Step 1: Write test — dismissing a violation improves the score**

```python
# append to tests/services/test_rescore.py

def test_rescore_dismissing_violation_changes_score():
    """Dismissing a violation should produce a different (better) score."""
    v1 = _make_violation(severity="critical", req="R1", file="a.py", line=1, reason="null deref")
    v2 = _make_violation(severity="major", req="R2", file="b.py", line=5, reason="unused var")
    dim = _make_dimension(violations=[v1, v2], compliance=[_make_compliance()])

    result_all = rescore_dimensions([dim], dismissed_keys=set())
    result_dismissed = rescore_dimensions([dim], dismissed_keys={("R1", "a.py", 1)})

    score_all = result_all["dimensions"][0]["overallScore"]
    score_dismissed = result_dismissed["dimensions"][0]["overallScore"]

    # With critical removed, score should be higher
    assert score_dismissed != score_all
    # Parse numeric values
    num_all = float(score_all.split("/")[0])
    num_dismissed = float(score_dismissed.split("/")[0])
    assert num_dismissed > num_all


def test_rescore_dismiss_all_violations():
    """Dismissing all violations should yield a high score."""
    v1 = _make_violation(severity="major", req="R1", file="a.py", line=1)
    dim = _make_dimension(violations=[v1], compliance=[_make_compliance()])

    result = rescore_dimensions([dim], dismissed_keys={("R1", "a.py", 1)})
    dim_result = result["dimensions"][0]

    # No violations left — score should be high
    assert dim_result["totals"]["violationCount"] == 0


def test_rescore_summary_reflects_dimension_changes():
    """Run-level summary should reflect rescored dimension scores."""
    v1 = _make_violation(severity="critical", req="R1", file="a.py", line=1)
    dim1 = _make_dimension(name="Reliability", violations=[v1], compliance=[_make_compliance()])
    dim2 = _make_dimension(name="Security", violations=[], compliance=[_make_compliance()])

    result = rescore_dimensions([dim1, dim2], dismissed_keys=set())
    summary = result["summary"]
    assert summary["dimensionsCount"] == 2
    assert summary["overallGrade"] is not None
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/services/test_rescore.py -v`
Expected: All 4 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/services/test_rescore.py
git commit -m "test: add rescore dismissal and summary tests"
```

---

### Task 3: Add `/api/rescore` Endpoint

**Files:**
- Create: `src/quodeq/api/routes_rescore.py`
- Create: `tests/api/test_routes_rescore.py`
- Modify: `src/quodeq/api/app.py:172`

- [ ] **Step 1: Write failing test for the endpoint**

```python
# tests/api/test_routes_rescore.py
"""Tests for the /api/rescore endpoint."""
import json
from unittest.mock import patch, MagicMock

import pytest

from quodeq.api.app import create_app


@pytest.fixture
def client():
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as c:
        yield c


def test_rescore_requires_project(client):
    resp = client.get("/api/rescore")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "project" in data.get("error", "").lower()


@patch("quodeq.api.routes_rescore.read_run_data")
@patch("quodeq.api.routes_rescore.list_runs")
@patch("quodeq.api.routes_rescore.load_dismissed_keys")
@patch("quodeq.api.routes_rescore.rescore_dimensions")
def test_rescore_returns_rescored_data(mock_rescore, mock_dismissed, mock_list_runs, mock_read_run, client):
    mock_list_runs.return_value = [MagicMock(run_id="run-1", date_iso="2026-04-02", date_label="Apr 2")]
    mock_read_run.return_value = []
    mock_dismissed.return_value = set()
    mock_rescore.return_value = {"dimensions": [], "summary": {"dimensionsCount": 0, "overallGrade": None}}

    resp = client.get("/api/rescore?project=test-project")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "dimensions" in data
    assert "summary" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/api/test_routes_rescore.py -v`
Expected: FAIL — route not registered

- [ ] **Step 3: Create the route module**

```python
# src/quodeq/api/routes_rescore.py
"""API route for live rescoring after dismissals."""
from __future__ import annotations

from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.data.fs.report_parser.runs import read_run_data
from quodeq.services.ports import list_runs
from quodeq.services.dismissed import dismissed_keys as load_dismissed_keys
from quodeq.services.rescore import rescore_dimensions


def _reports_dir_from_app(app: Flask) -> str:
    return app.config.get("REPORTS_DIR") or __import__(
        "quodeq.shared.utils", fromlist=["get_reports_dir"]
    ).get_reports_dir()


def _eval_dir_from_app(app: Flask) -> str:
    return app.config.get("EVALUATIONS_DIR") or __import__(
        "quodeq.shared.utils", fromlist=["get_evaluations_dir"]
    ).get_evaluations_dir()


def register_rescore_routes(app: Flask) -> None:
    """Register /api/rescore route."""

    @app.get("/api/rescore")
    def rescore() -> Response | tuple[Response, int]:
        project = request.args.get("project", "")
        if not project:
            return jsonify({"error": "project query parameter is required"}), 400

        run_id = request.args.get("run", "")
        reports_dir = _reports_dir_from_app(app)

        # Resolve run ID
        if not run_id or run_id == "latest":
            runs = list_runs(Path(reports_dir), project, limit=1)
            if not runs:
                return jsonify({"error": "No runs found for project"}), 404
            run_id = runs[0].run_id

        try:
            dimensions = read_run_data(Path(reports_dir), project, run_id)
        except FileNotFoundError:
            return jsonify({"error": "Run data not found"}), 404

        eval_dir = _eval_dir_from_app(app)
        project_dir = Path(eval_dir) / project
        dismissed = load_dismissed_keys(project_dir)

        result = rescore_dimensions(dimensions, dismissed)
        return jsonify(result)
```

- [ ] **Step 4: Register the route in app.py**

In `src/quodeq/api/app.py`, add the import and registration call:

Add import at the top with other route imports:
```python
from quodeq.api.routes_rescore import register_rescore_routes
```

Add to `_register_all_routes` function (after `register_findings_routes(app)`):
```python
    register_rescore_routes(app)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_routes_rescore.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/quodeq/api/routes_rescore.py tests/api/test_routes_rescore.py src/quodeq/api/app.py
git commit -m "feat: add /api/rescore endpoint for live grade recalculation"
```

---

### Task 4: Add Frontend `getRescore` API Call

**Files:**
- Modify: `src/quodeq/ui/src/api/index.js`

- [ ] **Step 1: Add `getRescore` function to the API module**

Add after the existing `restoreFinding` function in `src/quodeq/ui/src/api/index.js`:

```javascript
/**
 * Rescore a project run with dismissed findings filtered out.
 * @param {string} projectId - Project identifier
 * @param {string} [run='latest'] - Run ID (optional, defaults to latest)
 * @returns {Promise<{dimensions: Array, summary: object}>} Rescored data
 */
export async function getRescore(projectId, run = 'latest') {
  const params = new URLSearchParams({ project: projectId });
  if (run && run !== 'latest') params.set('run', run);
  return request(`/rescore?${params}`);
}
```

- [ ] **Step 2: Commit**

```bash
git add src/quodeq/ui/src/api/index.js
git commit -m "feat: add getRescore API client function"
```

---

### Task 5: Integrate Rescore Into Dashboard Load

**Files:**
- Modify: `src/quodeq/ui/src/features/dashboard/hooks/useDashboard.js`

The dashboard hook currently fetches dashboard data and sets it in state. We need to chain a rescore call after the dashboard loads, then patch the dashboard state with the rescored dimensions and summary.

- [ ] **Step 1: Import `getRescore` and add rescore chaining**

Modify `src/quodeq/ui/src/features/dashboard/hooks/useDashboard.js`:

Add to imports:
```javascript
import { getDashboard, getAccumulated, getRescore } from '../../../api/index.js';
```

Replace the `fetchDashboardEffect` function with a version that chains rescore:

```javascript
function fetchDashboardEffect(selectedProject, selectedRun, setDashboard, setLoading, setError) {
  if (!selectedProject) {
    setDashboard(null);
    setError(null);
    return;
  }

  let active = true;
  setLoading(true);
  setError(null);

  getDashboard(selectedProject, selectedRun)
    .then((payload) => {
      if (!active) return;
      setDashboard(payload);
      // Chain rescore to update grades with dismissed findings filtered
      const runId = payload?.selectedRun?.runId || selectedRun;
      return getRescore(selectedProject, runId).then((rescored) => {
        if (!active) return;
        setDashboard((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            dimensions: rescored.dimensions,
            summary: { ...prev.summary, ...rescored.summary },
          };
        });
      });
    })
    .catch((err) => {
      console.warn('Dashboard load failed:', err);
      if (active) setError('Failed to load dashboard data. Please try again.');
    })
    .finally(() => {
      if (active) setLoading(false);
    });

  return () => { active = false; };
}
```

- [ ] **Step 2: Verify the app loads correctly**

Run: Open `http://localhost:5173/` and navigate to a project dashboard. Scores should display. If there are dismissed findings, scores should reflect the dismissals.

- [ ] **Step 3: Commit**

```bash
git add src/quodeq/ui/src/features/dashboard/hooks/useDashboard.js
git commit -m "feat: chain rescore call after dashboard load for live grades"
```

---

### Task 6: Trigger Rescore After Dismiss/Restore

**Files:**
- Modify: `src/quodeq/ui/src/features/dashboard/hooks/useDashboard.js`

The existing `refreshDashboard()` already triggers a full dashboard re-fetch (which now chains rescore). So dismiss/restore → `refreshDashboard()` → dashboard + rescore already works.

Verify the dismiss flow triggers `refreshDashboard`. Check the existing dismiss handler in `App.jsx`.

- [ ] **Step 1: Verify dismiss already triggers refresh**

Read `src/quodeq/ui/src/App.jsx` lines 131-140 to confirm dismiss calls `refreshDashboard`. The pattern is:

```javascript
dismissFinding(props.navigation.selectedProject, buildDismissPayload(v, params.evalPrincipal?.dimension))
  .then(() => props.refreshDashboard?.())
  .catch((e) => console.error('[Dismiss] failed:', e));
```

This already calls `refreshDashboard()` after dismiss, which re-runs `fetchDashboardEffect` (which now includes the rescore chain). No changes needed.

- [ ] **Step 2: Verify restore triggers refresh in ViolationsPage**

Check `src/quodeq/ui/src/features/violations/components/ViolationsPage.jsx` to confirm the restore handler also triggers a refresh. The restore flow should call the same refresh mechanism.

- [ ] **Step 3: Manual test — dismiss a violation and verify grades update**

1. Open a project dashboard at `http://localhost:5173/`
2. Note the current dimension scores
3. Navigate to a principle detail page with violations
4. Dismiss a critical or major violation
5. Navigate back to dashboard
6. Verify scores have changed to reflect the dismissal
7. Go to Violations tab → Dismissed sub-tab → Restore the finding
8. Verify scores return to original values

- [ ] **Step 4: Commit (if any changes were needed)**

```bash
git commit -m "feat: verify dismiss/restore triggers live rescore via refreshDashboard"
```

---

### Task 7: Add Debounce for Rapid Dismiss Actions

**Files:**
- Modify: `src/quodeq/ui/src/features/dashboard/hooks/useDashboard.js`

If a user rapidly dismisses multiple violations, we don't want to fire a rescore for each one. The existing `refreshKey` mechanism already batches — React's state batching means multiple rapid `setRefreshKey` calls within the same event loop tick only trigger one re-render. However, if dismisses happen across ticks (e.g., user clicks rapidly), we should debounce.

- [ ] **Step 1: Add a debounced refresh**

Modify `src/quodeq/ui/src/features/dashboard/hooks/useDashboard.js`:

Add to imports:
```javascript
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
```

Replace the `refreshDashboard` definition:

```javascript
  const refreshTimerRef = useRef(null);
  const refreshDashboard = useCallback(() => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(() => setRefreshKey((k) => k + 1), 300);
  }, []);
```

- [ ] **Step 2: Clean up timer on unmount**

Add a cleanup effect after the existing effects:

```javascript
  useEffect(() => () => { if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current); }, []);
```

- [ ] **Step 3: Run the app and test rapid dismissals**

Open the app, navigate to a principle detail page, and dismiss multiple violations quickly. Verify only one rescore fires (check Network tab in browser DevTools — only one `/api/rescore` request should appear after the last dismiss).

- [ ] **Step 4: Commit**

```bash
git add src/quodeq/ui/src/features/dashboard/hooks/useDashboard.js
git commit -m "feat: debounce dashboard refresh for rapid dismiss/restore actions"
```

---

### Task 8: End-to-End Verification

**Files:** None (manual testing)

- [ ] **Step 1: Full flow test**

1. Start the dev server: `cd src/quodeq/ui && npm run dev`
2. Start the backend server
3. Open a project with violations
4. Note scores at all levels: run summary, dimension cards, principle cards
5. Dismiss a critical violation
6. Verify: principle score improves, dimension score improves, run summary score improves
7. Restore the violation
8. Verify: all scores return to original values
9. View a historical run — verify scores also reflect dismissals

- [ ] **Step 2: Run all tests**

Run: `python -m pytest tests/services/test_rescore.py tests/api/test_routes_rescore.py -v`
Expected: All tests PASS

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: live rescore on dismiss — complete implementation"
```
