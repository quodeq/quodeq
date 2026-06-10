# The Quodeq Evaluation Q² Formula

## Overview

Quodeq computes quality scores on a 0-10 scale for each evaluation principle (e.g., Analyzability, Reusability) within a quality dimension (e.g., Maintainability). The scoring model uses four independent constraints that work together to produce fair, interpretable grades.

## The Four Constraints

### 1. Violation Base

The base score reflects how bad the violations are, ignoring compliance entirely.

```
base = 10 / (1 + K * weighted_violations)
```

- **K = 0.12** controls sensitivity
- Uses severity-weighted violation type counts: `critical = 4.0`, `major = 1.5`, `minor = 0.25`
- Produces diminishing returns: the first violations hurt most, additional ones have decreasing impact
- Examples: 3 critical types (wv=12) -> base 4.1, 5 major types (wv=7.5) -> base 5.3

This is a hyperbolic curve inspired by CISQ's density-based approach, where the Nth violation matters less than the 1st.

### 2. Compliance Lift

Compliance evidence fills the gap between the base and the maximum score of 10.

```
lift = (compliance_count / (compliance_count + weighted_violations)) ^ compress
```

- **compress = 1.8** makes the top hard to reach (asymmetric curve)
- Compliance is counted uniformly (each item = 1 regardless of severity)
- The lift is a fraction [0, 1] of the gap `(10 - base)` that gets filled

Final raw score before constraints: `raw = base + (10 - base) * lift`

Properties:
- Compliance always helps (monotonic — more compliance = higher score)
- Compliance never hurts (lift >= 0)
- Reaching Exemplary requires a strong compliance-to-violation ratio
- With zero compliance, score equals the base

### 3. Violation Ceiling

The maximum achievable score is capped based on the weighted violation count.

```
ceiling = 10 - log2(1 + weighted_violations) * scale
```

- **scale = 0.5** controls how aggressively violations cap the score
- Uses weighted violations (not raw count), so minor violations barely affect the ceiling while major/critical violations bring it down
- Prevents the scenario where massive compliance overrides significant violations
- Examples: 10 minor (wv=2.5) -> ceiling 9.1, 21 minor (wv=5.2) -> ceiling 8.7

### 4. Severity Grade Floor

The grade label cannot be worse than the violation severities justify.

| Worst severity present | Minimum grade | Minimum score |
|---|---|---|
| None | Exemplary | 10.0 |
| Minor only | Adequate | 5.0 |
| Major (no critical) | Poor | 3.0 |
| Critical | (no floor) | 0.0 |

This means:
- 50 minor violations with zero compliance scores 5.0 (Adequate), not 0.0 (Critical) — because there are no critical or major violations to justify a "Critical" or "Poor" grade
- 10 major violations with zero compliance can score as low as 3.0 (Poor), but not "Critical"
- Only the presence of actual critical violations unlocks the "Critical" grade

Compliance can still lift a score above the floor. A principle with critical violations and strong compliance can achieve a Good or even Exemplary grade — the floor only prevents unfair downgrades.

## Grade Thresholds

| Score | Grade |
|---|---|
| >= 9.0 | Exemplary |
| >= 7.0 | Good |
| >= 5.0 | Adequate |
| >= 3.0 | Poor |
| < 3.0 | Critical |

A special "Insufficient" grade is assigned when confidence is too low to score (e.g., too few findings to draw conclusions).

## Scoring Pipeline

```
evidence -> tally violation types -> tally compliance types
         -> violation_base(vt_counts)             [stage 1]
         -> compliance_lift(ct_counts, vt_counts)  [stage 2]
         -> raw = base + (10 - base) * lift
         -> violation_ceiling(vt_counts)            [stage 3]
         -> severity_grade_floor(vt_counts)         [stage 4]
         -> final = max(floor, min(ceiling, raw))
         -> grade = score_to_grade_label(final)
```

## Violation Type Counting

Violations are grouped into distinct types per severity bucket. When a violation taxonomy (`vt` field) is available, each unique `(severity, vt)` combination is one type. Without taxonomy, each unique `(severity, reason)` pair is one type.

This means 10 violations of the same type count as 1 type, preventing duplicate findings from inflating the deduction.

## Overall Score

The overall dimension score is a weighted average across all principle scores, excluding principles marked "Insufficient" (low confidence). Principle weights are configurable (default x1, configurable up to x3).

If more than 50% of principles are Insufficient, the overall score is flagged with low confidence.

## Tunable parameters

All Q² constants are wrapped by `ScoringParams` (`core/scoring/params.py`).
`DEFAULT_PARAMS` mirrors the constants in `_constants.py`; user overrides
persist at `~/.quodeq/grade_formula.json` (see `services/grade_formula.py`)
and are editable from Settings > Grade formula. Every scoring function takes
an explicit `params` argument; there is no global mutable configuration.
The confidence/insufficient-evidence gate is intentionally NOT part of
`ScoringParams`.

**Params-convention split:** public entry points take
`params: ScoringParams | None = None` and lazily load the saved file on first
call; internal helpers take `params: ScoringParams = DEFAULT_PARAMS` and must
be reached through a loading entry point so defaults and overrides stay
consistent.

## Design Rationale

The model was designed to address specific fairness issues observed in real evaluations:

1. **Linear accumulation is unfair.** The old model used `n * penalty` which meant 39 minor violations (e.g., "file is 313 lines") could obliterate a score just as badly as 39 critical security flaws. The hyperbolic base curve provides natural diminishing returns.

2. **Compliance should be additive, not just a discount.** The old model used compliance as a multiplier on deductions (max 15% discount). The new model makes compliance a direct score contributor that fills the gap between the base and 10.

3. **Grade names should match reality.** A "Critical" grade should mean there are actual critical violations. The severity floor ensures grade labels are semantically honest.

4. **The top should be hard to reach.** The compressed lift curve (exponent 1.8) and the violation ceiling (log2-based) together ensure that Exemplary requires genuinely clean code, not just a favorable ratio.

## Industry Influences

- **CISQ** — Violations per KLOC with severity weights; density normalization
- **SQALE/SonarQube** — Remediation cost as ratio of development cost
- **SIG/TUViT** — Benchmark-based percentile ranking
- **CodeScene Code Health** — Per-metric independent capping; no linear accumulation
