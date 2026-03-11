# Deduction-Only Scoring Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ratio-based scoring with deduction-only model: base=10, deduct for violations, gate low-confidence principles as "Insufficient".

**Architecture:** Two functions change in `scoring.py` (`_score_principle_numerical`, `_score_principle_graded`) — gate on `conf_level == "low"` then use fixed base. `_weighted_overall` skips Insufficient principles. Dead ratio-lookup code removed from `scoring_internals.py`.

**Tech Stack:** Python, pytest

**Verify command:** `.venv/bin/pytest tests/ -q --ignore=tests/test_action_api_health.py`

---

## Chunk 1: Tests and Implementation

### Task 1: Write failing tests for new scoring behavior

**Files:**
- Modify: `tests/engine/test_scoring.py`

- [ ] **Step 1: Add test helpers for high and low confidence evidence**

```python
def _make_evidence_with_confidence(
    confidence_level="high",
    violations=None,
    compliance=None,
    n_violations=1,
    n_compliance=2,
):
    """Build Evidence with explicit confidence level and finding counts."""
    viol = violations or [
        {"file": f"v{i}.ts", "line": i, "snippet": "eval(x)", "reason": "injection", "severity": "high", "vt": "code-injection"}
        for i in range(n_violations)
    ]
    comp = compliance or [
        {"file": f"c{i}.ts", "line": i, "snippet": "JSON.parse(x)", "reason": "safe"}
        for i in range(n_compliance)
    ]
    total = len(viol) + len(comp)
    pct = round(len(comp) / total * 100, 1) if total > 0 else 0.0
    pe = PrincipleEvidence(
        practice_id="ts-001",
        display_name="Avoid eval()",
        dimension="security",
        severity="high",
        violations=viol,
        compliance=comp,
        metrics={
            "total_instances": total,
            "compliant": len(comp),
            "violating": len(viol),
            "compliance_percentage": pct,
            "confidence_level": confidence_level,
            "is_balanced": len(viol) > 0 and len(comp) > 0,
        },
    )
    return Evidence(
        repository="test-repo",
        plugin_id="typescript",
        date="2026-03-03",
        source_file_count=100,
        files_read=50,
        coverage_pct=50.0,
        principles={"ts-001": pe},
    )
```

- [ ] **Step 2: Add test — low confidence → Insufficient (numerical)**

```python
def test_numerical_low_confidence_returns_insufficient():
    ev = _make_evidence_with_confidence(confidence_level="low")
    scores = score_evidence(ev, mode="numerical")
    ts001 = scores["principles"]["ts-001"]
    assert ts001["grade"] == "Insufficient"
    assert ts001["final_score"] == 0.0
```

- [ ] **Step 3: Add test — low confidence → Insufficient (graded)**

```python
def test_graded_low_confidence_returns_insufficient():
    ev = _make_evidence_with_confidence(confidence_level="low")
    scores = score_evidence(ev, mode="non-numerical")
    ts001 = scores["principles"]["ts-001"]
    assert ts001["grade"] == "Insufficient"
```

- [ ] **Step 4: Add test — high confidence, no violations → 10/10**

```python
def test_numerical_high_confidence_no_violations():
    ev = _make_evidence_with_confidence(
        confidence_level="high", violations=[], n_violations=0, n_compliance=10,
    )
    scores = score_evidence(ev, mode="numerical")
    ts001 = scores["principles"]["ts-001"]
    assert ts001["base_score"] == 10
    assert ts001["final_score"] == 10.0
    assert ts001["grade"] == "Exemplary"
```

- [ ] **Step 5: Add test — high confidence, violations → deductions from 10**

```python
def test_numerical_high_confidence_with_violations():
    ev = _make_evidence_with_confidence(
        confidence_level="high", n_violations=2, n_compliance=8,
        violations=[
            {"file": "a.ts", "line": 1, "snippet": "eval(x)", "reason": "r", "severity": "critical", "vt": "code-injection"},
            {"file": "b.ts", "line": 2, "snippet": "eval(y)", "reason": "r", "severity": "major", "vt": "unsafe-call"},
        ],
    )
    scores = score_evidence(ev, mode="numerical")
    ts001 = scores["principles"]["ts-001"]
    assert ts001["base_score"] == 10
    # 1 critical type (-1.0) + 1 major type (-0.5) = 8.5
    assert ts001["final_score"] == 8.5
```

- [ ] **Step 6: Add test — graded high confidence, no violations → Exemplary**

```python
def test_graded_high_confidence_no_violations():
    ev = _make_evidence_with_confidence(
        confidence_level="high", violations=[], n_violations=0, n_compliance=10,
    )
    scores = score_evidence(ev, mode="non-numerical")
    ts001 = scores["principles"]["ts-001"]
    assert ts001["base_grade"] == "Exemplary"
    assert ts001["grade"] == "Exemplary"
```

- [ ] **Step 7: Add test — weighted overall excludes Insufficient**

```python
def test_weighted_overall_excludes_insufficient():
    """A mix of Insufficient and scored principles: overall uses only scored ones."""
    pe_low = PrincipleEvidence(
        practice_id="p-low", display_name="Low Conf", dimension="security",
        severity="high", violations=[], compliance=[],
        metrics={"total_instances": 1, "compliant": 1, "violating": 0,
                 "compliance_percentage": 100.0, "confidence_level": "low", "is_balanced": False},
    )
    pe_high = PrincipleEvidence(
        practice_id="p-high", display_name="High Conf", dimension="security",
        severity="high",
        violations=[{"file": "a.ts", "line": 1, "snippet": "x", "reason": "r", "severity": "critical", "vt": "vt1"}],
        compliance=[{"file": "b.ts", "line": 2, "snippet": "y", "reason": "r"}] * 9,
        metrics={"total_instances": 10, "compliant": 9, "violating": 1,
                 "compliance_percentage": 90.0, "confidence_level": "high", "is_balanced": True},
    )
    ev = Evidence(
        repository="test", plugin_id="ts", date="2026-03-03",
        source_file_count=100, files_read=50, coverage_pct=50.0,
        principles={"p-low": pe_low, "p-high": pe_high},
    )
    scores = score_evidence(ev, mode="numerical")
    assert scores["principles"]["p-low"]["grade"] == "Insufficient"
    # Overall should reflect only p-high, not be dragged down by p-low
    assert scores["overall"]["weighted_score"] == scores["principles"]["p-high"]["final_score"]
```

- [ ] **Step 8: Add test — all Insufficient → overall Insufficient**

```python
def test_all_insufficient_overall():
    ev = _make_evidence_with_confidence(confidence_level="low")
    scores = score_evidence(ev, mode="numerical")
    assert scores["overall"]["grade"] == "Insufficient"
    assert scores["overall"]["weighted_score"] == 0.0
```

- [ ] **Step 9: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/engine/test_scoring.py -v`
Expected: new tests FAIL (old scoring logic doesn't match new assertions)

- [ ] **Step 10: Commit failing tests**

```bash
git add tests/engine/test_scoring.py
git commit -m "test: add failing tests for deduction-only scoring model"
```

---

### Task 2: Implement scoring changes

**Files:**
- Modify: `src/quodeq/engine/scoring.py:71-112` (two scoring functions)
- Modify: `src/quodeq/engine/scoring.py:190-229` (`_weighted_overall`)

- [ ] **Step 1: Change `_score_principle_numerical` — gate + base=10**

In `scoring.py`, replace `_score_principle_numerical`:

```python
def _score_principle_numerical(ctx: _PrincipleContext) -> dict:
    """Score a single principle in numerical mode."""
    if ctx.conf_level == "low":
        return {
            "display_name": ctx.pdata.get("display_name", ctx.key),
            "weight": ctx.pdata.get("weight", DEFAULT_WEIGHT),
            "compliance_percentage": ctx.pct,
            "base_score": 0,
            "deductions": build_deductions({}, scale_multiplier=ctx.scale_mult),
            "final_score": 0.0,
            "grade": "Insufficient",
            "taxonomy_used": ctx.using_taxonomy,
            "confidence_level": ctx.conf_level,
            "confidence_interval": ctx.ci["confidence_interval"],
            "grade_stability": ctx.ci["grade_stability"],
        }

    base_pts = 10
    deductions = build_deductions(ctx.vt_counts, scale_multiplier=ctx.scale_mult)

    effective_cap = min(deductions["critical_cap"], deductions["major_cap"])
    adjusted = min(effective_cap, round(base_pts - deductions["total_deduction"], 1))
    final_pts = max(0.0, min(10.0, adjusted))

    return {
        "display_name": ctx.pdata.get("display_name", ctx.key),
        "weight": ctx.pdata.get("weight", DEFAULT_WEIGHT),
        "compliance_percentage": ctx.pct,
        "base_score": base_pts,
        "deductions": deductions,
        "final_score": final_pts,
        "grade": score_to_grade_label(final_pts),
        "taxonomy_used": ctx.using_taxonomy,
        "confidence_level": ctx.conf_level,
        "confidence_interval": ctx.ci["confidence_interval"],
        "grade_stability": ctx.ci["grade_stability"],
    }
```

- [ ] **Step 2: Change `_score_principle_graded` — gate + base=Exemplary**

```python
def _score_principle_graded(ctx: _PrincipleContext) -> dict:
    """Score a single principle in non-numerical (graded) mode."""
    if ctx.conf_level == "low":
        return {
            "display_name": ctx.pdata.get("display_name", ctx.key),
            "weight": ctx.pdata.get("weight", DEFAULT_WEIGHT),
            "compliance_percentage": ctx.pct,
            "base_grade": "Insufficient",
            "severity_drops": 0,
            "grade": "Insufficient",
            "taxonomy_used": ctx.using_taxonomy,
            "confidence_level": ctx.conf_level,
            "confidence_interval": ctx.ci["confidence_interval"],
            "grade_stability": ctx.ci["grade_stability"],
        }

    base_label = "Exemplary"
    level_drops = count_grade_drops(ctx.vt_counts, scale_multiplier=ctx.scale_mult)
    final_label = drop_grade(base_label, level_drops)

    return {
        "display_name": ctx.pdata.get("display_name", ctx.key),
        "weight": ctx.pdata.get("weight", DEFAULT_WEIGHT),
        "compliance_percentage": ctx.pct,
        "base_grade": base_label,
        "severity_drops": level_drops,
        "grade": final_label,
        "taxonomy_used": ctx.using_taxonomy,
        "confidence_level": ctx.conf_level,
        "confidence_interval": ctx.ci["confidence_interval"],
        "grade_stability": ctx.ci["grade_stability"],
    }
```

- [ ] **Step 3: Change `_weighted_overall` — exclude Insufficient**

```python
def _weighted_overall(principles_scores: dict, mode: str) -> dict:
    total_weight = 0
    total_value = 0.0

    for pdata in principles_scores.values():
        if pdata.get("grade") == "Insufficient":
            continue
        multiplier = weight_as_multiplier(pdata.get("weight", DEFAULT_WEIGHT))
        total_weight += multiplier

        if mode == "numerical":
            total_value += pdata["final_score"] * multiplier
        else:
            grade_index = GRADE_LADDER.index(pdata["grade"])
            total_value += grade_index * multiplier

    if total_weight == 0:
        if mode == "numerical":
            return {"weighted_score": 0.0, "grade": "Insufficient"}
        return {"weighted_grade": "Insufficient"}

    if mode == "numerical":
        mean_score = round(total_value / total_weight, 1)
        return {
            "weighted_score": mean_score,
            "grade": score_to_grade_label(mean_score),
            "total_weight": total_weight,
        }
    else:
        mean_index = total_value / total_weight
        ladder_pos = min(len(GRADE_LADDER) - 1, round(mean_index))
        return {
            "weighted_grade": GRADE_LADDER[ladder_pos],
            "total_weight": total_weight,
        }
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/engine/test_scoring.py -v`
Expected: new tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/engine/scoring.py
git commit -m "feat: deduction-only scoring — base=10, gate low confidence as Insufficient"
```

---

### Task 3: Fix existing tests

**Files:**
- Modify: `tests/engine/test_scoring.py`
- Modify: `tests/engine/test_report.py`

Both test files use `_make_evidence()` helpers with `confidence_level: "low"`. Under the new model this produces "Insufficient" instead of a real score. The fix: change `confidence_level` to `"high"` in test helpers where real scoring is expected.

- [ ] **Step 1: Fix `test_scoring.py` — update `_make_evidence` confidence level**

In `tests/engine/test_scoring.py`, change the existing `_make_evidence()` helper:

```python
# Change this line in the metrics dict:
"confidence_level": "low",
# To:
"confidence_level": "high",
```

Also update `"total_instances": 3` to match the high confidence threshold. Since `source_file_count=100` → `scale_multiplier=1` → high threshold = 10. Update findings to have at least 10 instances, OR keep 3 instances with `confidence_level: "medium"` (medium is not gated).

Simplest fix: change to `"confidence_level": "medium"` (this is not gated, and doesn't require changing the finding counts).

- [ ] **Step 2: Fix `test_report.py` — update `_make_evidence` confidence level**

Same change in `tests/engine/test_report.py`:

```python
"confidence_level": "low",
# To:
"confidence_level": "medium",
```

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/pytest tests/ -q --ignore=tests/test_action_api_health.py`
Expected: 292+ tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/engine/test_scoring.py tests/engine/test_report.py
git commit -m "test: update test evidence to medium confidence for deduction-only model"
```

---

### Task 4: Remove dead ratio-based code

**Files:**
- Modify: `src/quodeq/engine/scoring_internals.py:11-31` (remove `_SCORE_BANDS`, `_GRADE_BANDS`)
- Modify: `src/quodeq/engine/scoring_internals.py:89-102` (remove `score_for_compliance`, `grade_for_compliance`)
- Modify: `src/quodeq/engine/scoring.py` (remove imports and `__all__` entries)

- [ ] **Step 1: Remove `_SCORE_BANDS` and `_GRADE_BANDS` from `scoring_internals.py`**

Delete lines 8-31 (the two constants and their comments).

- [ ] **Step 2: Remove `score_for_compliance` and `grade_for_compliance` from `scoring_internals.py`**

Delete the two functions (lines 89-102 approximately) and their comments.

- [ ] **Step 3: Remove imports from `scoring.py`**

Remove `grade_for_compliance` and `score_for_compliance` from the import block and from `__all__`.

- [ ] **Step 4: Run full test suite**

Run: `.venv/bin/pytest tests/ -q --ignore=tests/test_action_api_health.py`
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/engine/scoring_internals.py src/quodeq/engine/scoring.py
git commit -m "refactor: remove dead ratio-based scoring functions and constants"
```

---

### Task 5: Run full verification

- [ ] **Step 1: Run complete test suite**

Run: `.venv/bin/pytest tests/ -q --ignore=tests/test_action_api_health.py`
Expected: all tests pass, 0 failures

- [ ] **Step 2: Verify no remaining references to removed functions**

Run: `grep -r "score_for_compliance\|grade_for_compliance\|_SCORE_BANDS\|_GRADE_BANDS" src/ tests/`
Expected: no matches
