# Accuracy Benchmark Harness

**Date:** 2026-07-10
**Status:** Approved
**Branch:** feat/benchmark-harness (created off fresh develop at implementation start)

## Problem

Quodeq's product is a grade, but nothing in the repo measures whether the
grades — or the findings behind them — are correct. `evaluations/` holds two
sample runs, not ground truth. The scoring tests verify that the CLI and SQL
engines agree with each other (consistency), never that either is right
(correctness). Today we cannot answer:

- What is quodeq's precision/recall on SQL injection? On god functions?
- Did a prompt change in `src/quodeq/data/prompts/` improve or regress recall?
- Is a local `gemma3:27b` good enough, or does a user need Claude?

Every planned accuracy improvement (snippet grounding, adversarial verifier,
cross-file context) lands blind without an instrument to measure it. The
per-model accuracy table is also the single most valuable publishable artifact
for an open-source scanner that supports both local and cloud models — a
question no competitor answers honestly.

## Decision

Build a **black-box benchmark harness** under a top-level `benchmarks/`
directory, phased:

- **Phase 1 — CI regression gate.** Hand-authored synthetic corpus covering
  all 6 ISO 25010 dimensions; runs on PRs that touch prompts/analysis/
  standards; one pinned cheap cloud model; fails on metric regression against
  a committed baseline.
- **Phase 2 — published accuracy report.** Pinned external corpus (CVE-fix
  commits at the vulnerable ref, OWASP/Juliet subsets); manual/nightly sweep
  across all providers; per-model precision/recall tables for docs/README.
- **Phase 3 — corpus growth and variance.** Larger corpus; repeat-run
  variance (5×) published as error bars next to every number.

One harness, two run profiles. The harness never imports quodeq internals: it
shells out to `quodeq evaluate` and parses the artifacts quodeq already emits.

## Layout

```
benchmarks/
  corpus/
    synthetic/<case-id>/       # tiny hand-authored projects, one truth.json each
    external.json              # manifest of pinned real repos (never vendored)
  harness/                     # runner, matcher, reporter (plain Python, stdlib only)
  baselines/gate.json          # committed accuracy baseline for the CI gate
  results/                     # raw run artifacts (gitignored)
```

`benchmarks/` is dev/release tooling: excluded from the wheel, outside
`src/quodeq` and its layer rules (`tools/check_imports.py` untouched).

## Corpus and Ground Truth

### Synthetic cases (Phase 1)

Each case is a small self-contained project (5–40 files, single language)
seeded with known violations. Labels are **objective by construction**: we
planted the issue, so "did quodeq find it" has a right answer — this is what
makes ground truth possible for subjective dimensions (Maintainability,
Flexibility, Usability).

`truth.json` per case:

```json
{
  "language": "python",
  "exhaustive": true,
  "clean_files": [],
  "labels": [
    {"file": "src/db.py", "line": 15, "anchor": "f\"SELECT * FROM",
     "dimension": "security", "cwes": [89, 564], "reqs": [],
     "severity": "critical", "note": "f-string SQL"},
    {"file": "src/orders.py", "line": 40, "anchor": "def process_order",
     "dimension": "maintainability", "cwes": [], "reqs": ["M-MOD-1"],
     "severity": "major", "note": "god function"}
  ]
}
```

- `exhaustive: true` declares every real issue in the case is labeled. Only
  exhaustive cases (or declared-clean files) count toward false-positive
  metrics — otherwise unlabeled-but-real issues would pollute precision.
- Each label declares its **accepted classes** explicitly: `cwes` (list of
  CWE ids, any of which counts) and/or `reqs` (list of requirement IDs from
  `src/quodeq/data/standards/iso25010/*.json`, any of which counts). At
  least one of the two must be non-empty. The curator owns equivalence —
  no CWE hierarchy resolution (the shipped `audit.json` is a flat list with
  no parent/child data).
- `anchor` is a substring that must appear on the labeled line; the corpus
  integrity test verifies it, so mislabeled line numbers fail fast.
- Phase 1 target: 8–12 cases (roughly 5–40 files each), at least one per
  dimension, Python plus one other language.

### External corpus (Phase 2)

`external.json` pins real projects by commit — CVE-fix commits checked out at
the **vulnerable** ref, OWASP Benchmark / Juliet subsets:

```json
{
  "cases": [
    {"name": "flask-cve-2023-XXXX", "git_url": "https://...", "commit": "<sha>",
     "license": "BSD-3-Clause", "sparse_paths": ["src/"],
     "truth": {"exhaustive": false,
               "clean_files": ["src/utils/format.py"],
               "labels": [ ... ]}}
  ]
}
```

Repos are fetched into a local cache directory at run time and never vendored
(licensing). External labels are curated primarily for Security and
Reliability; FP measurement is restricted to `clean_files`.

## Matching Rule

A finding matches a label when **all** of:

1. **File** — same file after path normalization (repo-root-relative, POSIX
   separators, matching the evidence JSONL convention).
2. **Line window** — finding line within ±5 of the label line (or overlapping
   the label's `line..end_line` span when given).
3. **Class** — the finding's CWE refs intersect the label's `cwes` list, or
   the finding's `req` is in the label's `reqs` list. Labels declare all
   acceptable equivalents explicitly (see truth.json format); no hierarchy
   resolution is performed.

Severity is **not** part of the match; severity agreement is a secondary
metric. Multiple findings matching one label count as one true positive;
extras are tracked as duplicate rate, not penalized as FPs.

## Metrics

Per dimension × model:

| Metric | Definition |
|---|---|
| Recall | matched labels / total labels |
| Precision | matched findings / (matched + FP findings), FP counted only in exhaustive cases or clean files |
| F1 | harmonic mean of the above |
| FP density | FP findings per KLOC of clean/exhaustive code |
| Severity agreement | fraction of matched findings with the labeled severity |
| Duplicate rate | extra findings per matched label |

Compliance findings are ignored by the matcher in v1 (violations only).

## Harness Components

### Runner (`benchmarks/harness/`)

Takes a corpus selector × provider/model matrix. Per combination:

1. Materialize the case (copy synthetic dir / fetch+checkout external) into a
   temp workspace.
2. Run `quodeq evaluate <workspace> -d <dims> --clean-scan --output <tmp>`
   with the provider/model env (`AI_PROVIDER`, `AI_MODEL`), fixed time limit.
3. Parse `evidence/<dim>_evidence.jsonl` from the output dir.
4. Write `results/<run-id>/report.json` stamped with: model, provider,
   quodeq git commit, prompts hash (hash of `src/quodeq/data/prompts/` +
   compiled standards), timestamp, corpus revision, repetitions.

`--clean-scan` is mandatory: the permissive cache key
(`src/quodeq/analysis/cache/key.py`) excludes model/prompts/standards, so a
cached run would silently measure the wrong configuration.

A provider failure (CLI missing, API unreachable, timeout with zero evidence)
marks the run **errored**, never zero-recall — an unreachable model must be
distinguishable from a regression, and the CI gate reports it as an
infrastructure failure, not a metric failure.

### Comparer / Reporter

- `compare <baseline.json> <candidate.json>` — per-dimension metric deltas;
  exits non-zero when any dimension's precision or recall drops more than the
  threshold (default 5 points).
- Markdown emitter — renders the per-model accuracy table (per dimension:
  precision / recall / F1, plus error bars once Phase 3 variance exists) for
  docs and README.

## CI Regression Gate

`.github/workflows/benchmark.yml`:

- **Trigger:** PRs touching `src/quodeq/data/prompts/**`,
  `src/quodeq/analysis/**`, `src/quodeq/data/standards/**`, or
  `benchmarks/**`.
- **Scope:** synthetic corpus only.
- **Model:** one pinned Claude Haiku version (API key in Actions secrets),
  fixed temperature; the pinned model ID lives in `baselines/gate.json` so
  bumping it is an explicit, reviewed change.
- **Noise damping:** 2 repetitions, metrics averaged.
- **Gate rule:** fail if any dimension's recall or precision drops >5 points
  vs `baselines/gate.json`. Improvements are adopted by updating the baseline
  in the same PR (the workflow prints the refreshed baseline JSON).
- **Cost target:** <$1 per gated PR.
- Errored runs (provider/infra) fail the job with a distinct message and do
  not touch the baseline.

## Published Report (Phase 2)

A manually-triggered (later: nightly) workflow sweeps the full corpus
(synthetic + external) across providers: Ollama models (self-hosted runner or
local invocation), Claude, Codex, Gemini. Output: a dated markdown report per
sweep committed under `benchmarks/results/published/` (the one results
subdirectory that is tracked), feeding the docs/website accuracy table.

## Testing the Harness Itself

No model calls in the normal test suite:

- **Matcher unit tests** — fixture findings vs fixture truth: window edges,
  CWE-family resolution, duplicate collapsing, exhaustive-vs-not FP rules.
- **Reporter/comparer tests** — threshold logic, errored-run handling,
  baseline diff output.
- **Replay mode** — the runner accepts a directory of recorded evidence JSONL
  instead of invoking quodeq, exercising the full parse→match→report path
  deterministically. Recorded fixtures live under `tests/benchmarks/fixtures/`.

## Out of Scope (v1)

- Compliance-finding accuracy (violations only).
- Grade-level accuracy (we measure findings, not the Q² output; grade
  sensitivity is a separate effort).
- Multi-language breadth beyond two languages in Phase 1.
- Cross-file/dataflow-dependent labels (single-file labels only until the
  pipeline gains cross-file context).
- Automated label mining from CVE diffs (labels are hand-curated).

## Success Criteria

1. A PR changing `evaluation_rules.md` that tanks security recall on the
   synthetic corpus fails CI with a per-dimension metric diff.
2. `benchmarks/harness compare` reproduces identical numbers from identical
   evidence (deterministic given fixed inputs).
3. Phase 2 produces a per-model table (≥3 providers) publishable in README.
4. Harness plumbing is fully covered by the token-free test suite.
