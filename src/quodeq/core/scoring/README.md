# The Quodeq Evaluation Q² Formula

## Overview

Quodeq computes quality scores on a 0-10 scale for each evaluation principle (e.g., Analyzability, Reusability) within a quality dimension (e.g., Maintainability). The formula is a function of the set of (rule, file, severity) violations, the set of (rule, file) compliances, the project file count and the standard. All stages run per principle; principles then aggregate into a dimension, dimensions into the run.

## Terms

- `files`: the project's source file count for the run, floored at 100. Never the files read. When the count is unknown the spread multiplier is 1 for every requirement.
- `spread(n) = 1 + log2(1 + 100 * n / files)` for `n >= 1`, and `spread(0) = 0`. A rule hit in one file of 4,000 weighs 1.04; in 1 file per 100 weighs 2; in 300 of 2,800 files weighs 4.5; in every file weighs 7.7.
- Severity ladder minor < major < critical with weights `w_minor = 0.25`, `w_major = 2.0`, `w_critical = 4.0`. The weights must be strictly increasing.

## Constants

| Constant | Value |
|---|---|
| weight critical | 4.0 |
| weight major | 2.0 |
| weight minor | 0.25 |
| K | 0.08 |
| lift compress | 2.2 |
| ceiling scale | 0.5 |
| floor major-only | 3.0 |
| floor minor-only | 5.0 |

Sensitivity of the final grade to each constant, moved by 20% one at a time (mean absolute change over the fitting corpus; benchmark maximum; Exemplary share):

| Constant | 0.8x | 1.2x |
|---|---|---|
| weight major | 0.34, 2.8, 17.4% | 0.30, 2.4, 5.4% |
| K | 0.28, 2.9, 13.5% | 0.24, 2.3, 6.0% |
| lift compress | 0.22, 2.8, 11.7% | 0.17, 2.4, 6.1% |
| weight minor | 0.07, 2.6, 12.0% | 0.06, 2.6, 6.3% |
| weight critical | 0.04, 2.8, 7.7% | 0.03, 2.4, 7.6% |
| ceiling scale | 0.03, 2.6, 10.4% | 0.04, 2.6, 5.1% |

The major weight and K carry the formula; the ceiling scale and the minor weight decide who reaches Exemplary; the critical weight barely matters because criticals are rare and already dominate where they occur.

## The Four Stages

### 1. Violation Mass

Group the principle's non-dismissed violations by requirement code (fallback: the `vt` tag, then the free-text `reason`). For each requirement `r`:

- For each file `f` with a violation under `r`, `sev(r, f)` is the severity of that file's worst finding under `r`. Repeats of the same finding in the same file change nothing. A finding with no severity counts as minor.
- The severity is the finding's own: the model's rating as gated at scan time. The standard's suggested severity per requirement is shown to the model in its checklist and never applied here.
- `n_>=s(r)` is the number of files whose `sev(r, f)` is at least `s`.
- Cumulative mass: `w(r) = w_minor * spread(n_>=minor) + (w_major - w_minor) * spread(n_>=major) + (w_critical - w_major) * spread(n_>=critical)`.

When every file under `r` has the same severity `s` this is exactly `w_s * spread(n)`. When severities are mixed, each level adds the spread of the files that reach it. `violation_mass = sum of w(r)` over the requirements. The worst `sev(r, f)` present sets the floor.

### 2. Base and Compliance Lift

Compliance is grouped by requirement; `files_ok(r)` is the number of distinct files with compliance under `r`, and `compliance_mass = sum of spread(files_ok(r))`. Compliance is not severity-weighted: a followed critical rule and a followed minor rule count the same. This is a deliberate asymmetry, because inventing a compliance severity from the class would double-count the class.

```
base  = 10 / (1 + K * violation_mass)
lift  = (compliance_mass / (compliance_mass + violation_mass)) ^ compress
raw   = base + (10 - base) * lift
```

- **K = 0.08** controls how fast the base falls as mass grows; the curve has diminishing returns, so the first broken rules hurt most (inspired by CISQ's density-based approach).
- **compress = 2.2** makes the top hard to reach (asymmetric curve).
- The lift is a fraction [0, 1] of the gap `(10 - base)` that gets filled.

### 3. Violation Ceiling

```
ceiling = 10 - 0.5 * log2(1 + violation_mass)
```

- **scale = 0.5** controls how aggressively mass caps the score.
- Uses mass, not a raw count, so narrow minor rules barely move the ceiling while widespread major and critical rules bring it down.
- Prevents massive compliance from overriding significant violations.

### 4. Severity Grade Floor

The grade label cannot be worse than the worst effective severity justifies.

| Worst effective severity present | Minimum score |
|---|---|
| None | 10.0 |
| Minor | 5.0 |
| Major (no critical) | 3.0 |
| Critical | 0.0 |

`final = min(ceiling, max(floor, raw))`, rounded to one decimal. The ceiling beats the floor. The floor is the guard that makes grade labels honest (a Critical label needs a critical rule), not a working part of the curve: under the current constants it binds on none of the principles in the fitting corpus.

## Grade Thresholds

| Score | Grade |
|---|---|
| >= 9.0 | Exemplary |
| >= 7.0 | Good |
| >= 5.0 | Adequate |
| >= 3.0 | Poor |
| < 3.0 | Critical |

## Scoring Pipeline

```
evidence -> group violations and compliance by requirement, per file
         -> violation_mass(rows)                     [stage 1]
         -> compliance_mass(rows)
         -> base = 10 / (1 + K * violation_mass)     [stage 2]
         -> lift = (cm / (cm + vm)) ^ compress
         -> raw = base + (10 - base) * lift
         -> ceiling = 10 - 0.5 * log2(1 + vm)        [stage 3]
         -> floor from the worst effective severity  [stage 4]
         -> final = min(ceiling, max(floor, raw))
         -> grade = score_to_grade_label(final)
```

## Requirement Grouping

Violations and compliance are grouped by the first present of: the `req` requirement code (every finding carries one), the `vt` tag, the free-text `reason`. Ten findings under `M-MDF-1` are one requirement whatever their `vt` spelling. `vt` is a tag the model invents per finding and paraphrases between runs, so the requirement code leads (issue #1274). What a requirement weighs is decided by how many files it is broken in and by the standard's class, not by how many findings repeat inside a file.

## Aggregation

Within a dimension, principle scores are averaged weighted by **observation**: `obs = sum of spread(files observed under r)` over the principle's violated and complied rules, times the principle's configured multiplier (x1, x2, x3). Observation measures how much of the codebase the principle was seen on, not how bad it is; weighting by badness double-counts severity. A principle with 7 findings therefore no longer carries the weight of one with 2,329.

Across dimensions the configurable dimension weights apply, and failure-streak dimensions stay out of the overall. The graded (non-numerical) legacy mode is untouched.

## Thin Evidence

Every principle with at least one instance is scored and enters the dimension average with its observation weight. The confidence level (high, medium, low) is computed from the instance count against a size-scaled threshold, but it is a **thin-evidence marker** carried beside the score, not a grade. The dimension's low-confidence note is shown when more than half of the dimension's observation weight comes from low-confidence principles. A principle with zero instances remains unscored.

## Properties

| # | Property |
|---|---|
| P1 | Adding a violation never raises a principle's score; removing one (fixing, dismissing) never lowers it |
| P2 | Adding a compliance never lowers the score |
| P3 | Raising one finding's severity never raises the score |
| P4 | A model repeating a finding (same rule, file) or a compliance changes nothing |
| P5 | Doubling the project (every file and finding twice, file count twice) changes nothing, for projects at or above the 100-file floor |
| P6 | Raising a rating never raises the score |
| P7 | No cliff from evidence volume: thin evidence is marked, not gated |
| P8 | A grade label is never worse than the worst effective severity allows |

Known non-properties, accepted: the same location filed under two different rules counts twice (no dedup); floors are a discontinuity in severity, and a single rating can flip them; the mass of a rule follows the model's per-file severities, so two models that rate differently grade differently, by design.

## Tunable parameters

All Q² constants are wrapped by `ScoringParams` (`core/scoring/params.py`).
`DEFAULT_PARAMS` mirrors the constants in `constants.py`; user overrides
persist at `~/.quodeq/grade_formula.json` (see `services/grade_formula.py`)
and are editable from Settings > Grade formula. Every scoring function takes
an explicit `params` argument; there is no global mutable configuration.
The confidence level (the thin-evidence marker) is intentionally NOT part of
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

4. **The top should be hard to reach.** The compressed lift curve (exponent 2.2) and the violation ceiling (log2-based) together ensure that Exemplary requires genuinely clean code, not just a favorable ratio.

## Industry Influences

- **CISQ**: Violations per KLOC with severity weights; density normalization
- **SQALE/SonarQube**: Remediation cost as ratio of development cost
- **SIG/TUViT**: Benchmark-based percentile ranking
- **CodeScene Code Health**: Per-metric independent capping; no linear accumulation
