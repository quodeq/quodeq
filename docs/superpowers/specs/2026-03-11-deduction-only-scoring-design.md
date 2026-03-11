# Deduction-Only Scoring Model

## Problem

The current scoring model computes a **base score from the compliance/violation ratio**:

```
compliance_pct = compliance_count / (compliance_count + violation_count)
base_score = score_for_compliance(compliance_pct)    # 70%→10, 30%→6, 5%→2
final_score = base_score - violation_deductions
```

This makes the score a property of the AI's output volume, not the code's quality. Two AI runs on identical code can report different finding counts and produce different scores. The prompt previously nudged the AI to "aim for at least 30% compliance findings" to stabilize the ratio — an artificial target that incentivizes fabrication and undermines ground-truth reporting.

## Solution: Deduction-Only with Coverage Gate

**Base score = 10 (always).** Deductions from violations bring it down. Compliance findings are evidence of thoroughness but do not inflate or deflate the score.

**Coverage gate:** If `confidence_level == "low"` (fewer than 5 × scale_multiplier total findings for a principle), the principle gets grade "Insufficient" — no score. This prevents under-analyzed principles from silently receiving 10/10.

**Confidence intervals** (existing system) communicate remaining uncertainty for medium-confidence principles. No new penalty mechanisms — the score is the best estimate; the confidence metadata says how much to trust it.

## Design

### 1. Prompt changes (`prompts/compass.md`)

Already applied:

- **Removed** "Min findings target" column from the project size table (was a fabrication incentive).
- **Removed** "Aim for at least 30% compliance findings" line.
- **Replaced** "Balanced Evidence" section with "Systematic Evaluation": evaluate every file against every applicable principle, report all findings, no ratio targets.

### 2. Scoring model (`scoring_internals.py` + `scoring.py`)

#### Numerical mode (`_score_principle_numerical`)

Before:
```python
base_pts = score_for_compliance(ctx.pct)
```

After:
```python
if ctx.conf_level == "low":
    return {... "final_score": 0.0, "grade": "Insufficient", ...}
base_pts = 10
```

The rest is unchanged: `build_deductions(vt_counts, scale_multiplier)` computes severity-weighted deductions, `final = max(0, min(10, base - deductions))`.

#### Graded mode (`_score_principle_graded`)

Before:
```python
base_label = grade_for_compliance(ctx.pct)
```

After:
```python
if ctx.conf_level == "low":
    return {... "grade": "Insufficient", ...}
base_label = "Exemplary"
```

The rest is unchanged: `count_grade_drops()` and `drop_grade()` apply severity-based level drops.

#### Dead code removal

- `_SCORE_BANDS` constant — remove (no longer used in scoring path).
- `_GRADE_BANDS` constant — remove.
- `score_for_compliance()` function — remove.
- `grade_for_compliance()` function — remove.

### 3. Weighted overall (`_weighted_overall`)

Principles with `grade == "Insufficient"` are **excluded** from the weighted average.

- If some principles are Insufficient: average computed from remaining principles only.
- If ALL principles are Insufficient: overall grade = "Insufficient", overall score = None.

Rationale: "Insufficient" means "not enough data," not "score 0." Including it as 0 would conflate bad code with insufficient evidence and create a perverse incentive (under-reporting violations to get Insufficient instead of a low score).

### 4. Evidence model (`evidence.py`)

No changes. `PrincipleEvidence.compute_metrics()` already computes `confidence_level` with scaled thresholds. The confidence level is now the scoring gate rather than just a label.

### 5. Report output (`report.py`)

No structural changes. `build_report_json()` reads `final_score` and `grade` from scoring output — same fields, different values. `compliance_percentage` remains in per-principle output as transparency metadata.

### 6. Dashboard/accumulated views

No changes needed:
- `most_frequent_grade()` handles any grade string including "Insufficient".
- `parse_numeric_score()` handles 0.0.
- `numeric_average()` should be verified to handle the case where all principles are Insufficient (returns None).

## Files to modify

| File | Change |
|------|--------|
| `prompts/compass.md` | Already done — systematic evaluation, no ratio targets |
| `src/quodeq/engine/scoring_internals.py` | Remove `_SCORE_BANDS`, `_GRADE_BANDS`, `score_for_compliance()`, `grade_for_compliance()` |
| `src/quodeq/engine/scoring.py` | Gate on low confidence → Insufficient; base=10 / base=Exemplary; skip Insufficient in `_weighted_overall` |
| Tests | Update assertions for base_score=10, Insufficient gating, weighted average exclusion |

## Scoring behavior examples

| Principle state | Old model | New model |
|----------------|-----------|-----------|
| 0 findings | 0/10 (0% compliance) | Insufficient (gated) |
| 3 compliance, 0 violations (low conf) | 10/10 (100% compliance) | Insufficient (gated) |
| 8 compliance, 2 violations (minor) | 8/10 base, minor deductions | 10/10 base, minor deductions |
| 5 compliance, 5 violations (1 critical) | 5/10 base, -1.0 critical | 10/10 base, -1.0 critical, cap at 3 if saturated |
| 50 compliance, 50 violations | 5/10 base | 10/10 base (deductions determine score) |
