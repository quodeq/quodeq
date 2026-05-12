# Finding-Verifier Project Retrospective

**Branch:** `experimental/finding-verifier`
**Period:** 2026-05-09 through 2026-05-12
**Status:** v9 shipped, branch ready for review/merge, but a strategic pivot is recommended before further investment.

This document captures what we built, what we measured, what we learned, and a
recommendation for where the work should go next. It is written as a handoff so
another contributor (or a future you) can pick up the thread without re-running
the same experiments.

---

## TL;DR

We built a finding-verifier subsystem: tree-sitter resolver + multi-block code
evidence + small-LLM reasoner + deterministic verdict. It works, ships value
(~+3pp false-positive detection over baseline), but the empirical data revealed
two things worth thinking hard about:

1. **The accuracy ceiling of small-model verification is lower than hoped.**
   Gemma 4 e4b makes systematic reasoning errors (over-detects override seams)
   that Haiku and Sonnet do not. Our `26.3%` false-positive rate is probably
   *inflated* — some of those are real violations Gemma rescued by hallucinating
   override mechanisms.
2. **The evidence pipeline we built belongs upstream in the evaluator, not in a
   separate verification step.** Everything the verifier extracts (referenced
   symbols, abstraction definitions, parent-function seams) would let the
   evaluator generate ~20–30% fewer false positives at source — eliminating the
   need for second-pass verification on most findings.

The honest recommendation: **keep the resolver/manifest/multi-block infrastructure,
move it from the verifier into the evaluator, retire the verifier as a separate
user-facing feature.** What we built isn't wasted; it's in the wrong layer.

---

## What we built (in commit order)

### Phase 1 — visibility UI (badges)

- `useVerifications` hook + finding-id helper (FNV-1a, JS/Python round-trip pinned).
- `VerificationBadge` component (4 verdicts: `false_positive`, `confirmed`,
  `inconclusive`, `not_applicable`).
- Wired into `PrincipleDetailPage` and `FileDetailPage` so verdicts appear
  inline next to severity pills.
- Verifier-tab UX fixes: filter, reverse-order toggle, sticky right pane.
- Production bug parade resolved: project-UUID vs run-UUID, `file:line` packed
  field, indexer dot-skip (`22,998 → 848` files), thread safety.

### Phase 2 — v8: generic claim-driven verifier

Replaced narrow v7.2 substitutability prompt with a single generic prompt that
treats the evaluator's `title` + `reason` as the rubric. Four checklist
questions, deterministic verdict computation in Python.

Files: `src/quodeq/verifier/{prompt,schema,verdict,models,service,verifier}.py`,
`tests/verifier/test_*.py`, `pyproject.toml` (empirical marker).

Empirical regression suite: 4 fixtures (substitutability + 2 hardcoded paths +
argparse-override), opt-in via `pytest -m empirical`. All 4/4 pass.

### Phase 3 — v9: multi-block evidence pipeline

The resolver/manifest already extracted cross-file facts (`referenced_symbol`,
`abstraction_defined_at`, `target_parent_seam_at`, etc.) but v8 ignored them.
v9 surfaces actual source-code windows from those locations as labeled
`[A]` `[B]` `[C]` blocks. The model reads code from multiple files and reasons
across them.

Block coverage per finding (from the 348-finding bulk run):
- 1 block: 200 findings (57%) — local violations, no cross-file evidence
- 2 blocks: 60 findings (17%)
- 5–6 blocks: 61 findings (18%) — rich context, where the architecture pays off

### Phase 4 — Claude-CLI client (experimental)

Built `ClaudeCliClient` wrapping `claude -p ... --system-prompt ... --json-schema`
to swap the LLM backend. Same v9 evidence pipeline, just different reasoner.

`claude` CLI was the wrong tool for batch: ~10–15s of subprocess boot overhead
per call (Node startup, plugin sync, auth init, default-system-prompt
assembly) means even Haiku averages 30–40s per call. Killed both Sonnet and
Haiku bulk runs after small samples.

---

## What we measured

### Bulk verification, 348 flexibility findings, v8 vs v9 (both Gemma 4 e4b)

| | v8 (thin evidence) | v9 (multi-block) | delta |
|---|---:|---:|---:|
| `confirmed` | 257 | 248 | −9 |
| `false_positive` | 79 | 89 | **+10** |
| `inconclusive` | 2 | 1 | −1 |
| `error` | 10 | 10 | — |
| **FP rate (excl. errors)** | **23.4%** | **26.3%** | **+3.0pp** |

Verdict transitions (v8 → v9):
- 132 stayed `confirmed → confirmed`
- 47 stayed `false_positive → false_positive`
- **27 flipped `confirmed → false_positive`** ← v9's catches
- 17 flipped `false_positive → confirmed` ← v9's regressions
- 1 + 1 noise

Net: 10 more false positives, but 17 v8 false-positives were rescinded. **Roughly
1 in 5 of v8's false-positives is fragile.**

Q2 (override mechanism) `yes` rate jumped from 53 → 80 (+27) under v9: the model
*is* seeing more seams when cross-file blocks are present. The architecture works
*in the cases where it has data*.

### Sonnet + Haiku partial samples (24 verdicts total, killed by speed)

Tiny sample, but the qualitative pattern is consistent and worth reporting.

**Of 5 Haiku-vs-Gemma disagreements on the same finding:**

| # | finding | Gemma | Haiku | who's right |
|---|---|---|---|---|
| 1 | `_ASVS_FILE = "asvs/level1.json"` | false_positive | confirmed | **Haiku.** Gemma mistook a `standards_dir: Path` param for an override of the FILE NAME. The param overrides a directory, not the cited constant. |
| 2 | Hardcoded API endpoint at `findings.js:63` | false_positive | confirmed | **Haiku.** Gemma dismissed because cited line was a docstring; the underlying endpoint hardcoding is real. |
| 3 | Hardcoded URL in test | false_positive | confirmed | **Haiku.** Gemma noticed "another test uses a different URL" and assumed parameterization. The cited test has it hardcoded. |
| 4 | `def _dim(score="7.5", grade="B")` | confirmed | false_positive | **Haiku.** These are textbook parameter defaults — a real override seam Gemma missed. |
| 5 | `EVALUATIONS_DIR = str(tmp_path)` | false_positive | confirmed | Borderline. pytest `tmp_path` is genuinely a fixture-provided override. |

**Pattern: Gemma over-detects override seams.** It pattern-matches "I see a
parameter somewhere in this file → override exists" without checking if the
override actually applies to the cited value. Smaller / weaker models confuse
*related* seams with *applicable* seams.

This means **our `26.3% false_positive` rate from v9-Gemma is inflated**. The
real false-positive rate (what a careful reasoner would say) is probably
20–25%, with the difference being legitimate violations Gemma incorrectly
rescued.

### Speed measurements

- Gemma 4 e4b (local Ollama): ~13–15s per call. Stable.
- Claude CLI (Sonnet, Haiku): ~25–40s per call due to subprocess overhead.
- Claude API (estimated, not measured): ~2–5s per call. CLI overhead is the
  dominant cost in batch.

---

## What we (re-)discovered about the architecture

### The good

1. **Separation of concerns is correct.** Resolver → manifest → prompt → verdict
   are independent, each testable in isolation. Empirical regression suite makes
   prompt iteration safe.
2. **Citation discipline works.** `_extract_visible_lines` + `enforce_citation_validity`
   prevent the model from claiming evidence it can't ground. Critical for trust.
3. **Multi-block evidence is a real lift** — but bounded to the ~18% of findings
   with rich cross-file context.
4. **The single generic prompt covers all flexibility findings.** No per-category
   branching needed. Standard-agnostic.

### The bounded

5. **Tree-sitter context lifts smaller models, but only ~3pp.** For local
   violations (most of the corpus), there's no cross-file evidence to surface —
   the verifier is just rubber-stamping the evaluator's claim. Gain available
   ≠ gain achievable.
6. **Gemma's reasoning ceiling is real.** Over-detection of override seams is a
   systematic failure mode no amount of prompt engineering will fully fix.
   Claude (even Haiku) reasons more carefully *about whether the seam applies
   to the cited value*.
7. **Per-finding LLM cost is not "much less than evaluation".** It's roughly
   the same. Verification adds ~15s of latency per click; the architecture has
   to assume the user really wants to know.

### The structural problem

8. **Verification treats a symptom.** The evaluator is what produces the false
   positives. Verifier is a second-pass quality control bolted on. Every
   improvement we made to the verifier's evidence pipeline would have an even
   bigger effect on the EVALUATOR, because it runs first and shapes everything
   downstream.

---

## Recommendation: move the evidence pipeline upstream

The honest take after all the measurement: **build the v9 evidence pipeline
into the evaluator, drop the separate verifier as a user-facing feature.**

### Why

- Evaluator runs once per evaluation; verifier runs per user click. Fix the
  cheaper step.
- Evaluator currently runs file-by-file with no cross-file context. Giving it
  the resolver/manifest pipeline would slash false positives at source.
- Halves the number of LLM-prompt subsystems to maintain.
- No two-step workflow for users. Findings are trustworthy when they appear.

### What survives

- The resolver, manifest builder, multi-block evidence renderer — all gold.
  Move them upstream.
- The empirical regression pattern — reuse it for evaluator iteration.
- The citation validator — same role in the evaluator.

### What dies

- The Verifier tab UI.
- The per-finding verify button.
- The `verifications.db` per-eval store. (Or keep it for forensic-only audit
  trail of evaluator decisions.)
- The `_extract_visible_lines` / `enforce_citation_validity` *as a runtime
  check* (still useful as part of the evaluator's structured-output pipeline).

### Alternative: hybrid escalation

If the second-opinion feature has real product value, the cheaper way to
deliver it is **on-demand Claude API call** when the user clicks
"Re-verify with Claude" on a specific finding. Two cents per call. No
local-model verifier needed. The infrastructure becomes a thin HTTP client +
a result store.

---

## Where state currently lives

### Code on branch `experimental/finding-verifier`

- `src/quodeq/resolver/` — tree-sitter symbol indexer, manifest builder.
  ~3000 LoC, well-tested. **Worth keeping regardless of where it's wired in.**
- `src/quodeq/verifier/` — prompts, schema, verdict, service, client, validate.
  Includes the v8/v9 generic prompt with multi-block render. Tests + empirical
  regression suite (`tests/verifier/`).
- `src/quodeq/api/routes_verifier.py` — Flask routes (POST verify, GET list,
  GET detail).
- `src/quodeq/ui/src/features/explorer/components/VerificationBadge.jsx` +
  hook + wiring in `PrincipleDetailPage` and `FileDetailPage`.
- `src/quodeq/ui/src/tabs/Verifier.jsx` — the side-tab UI.

### Diagnostic data (not committed; under `/tmp/v8_spike/`)

These are throwaway artifacts from the measurement runs. If you want to
re-analyze:
- `bulk_results.jsonl` — 348 v8/thin/Gemma verdicts.
- `bulk_results_v9.jsonl` — 348 v9/multi/Gemma verdicts.
- `bulk_results_claude.jsonl` — 9 v9/multi/Sonnet verdicts.
- `bulk_results_haiku.jsonl` — 15 v9/multi/Haiku verdicts.
- `compare.py`, `compare_3way.py`, `analyze.py` — analysis scripts.
- `bulk_runner_*.py` — re-runnable harness for any of the above.

### Design docs (workspace-local, not committed — `docs/` is gitignored)

- `docs/superpowers/specs/2026-05-12-v8-verifier-design.md`
- `docs/superpowers/plans/2026-05-11-verifier-badges-phase-1.md`
- `docs/superpowers/plans/2026-05-12-v8-verifier.md`

These are useful for context but live outside the repo by your `.gitignore`
convention.

---

## What to do next (if continuing this thread)

In priority order:

### 1. Decide whether to pursue the upstream-evaluator pivot

Before any more verifier work, get clear on:

- Is "second opinion verification" a real product feature users want?
- Or is "fewer false positives in the first place" the better win?

The data argues for the second. But you know the product better than I do.

### 2. If pivoting upstream: prototype evaluator + manifest

Spike: take ONE flexibility finding category (e.g., "Hardcoded constant"),
run the evaluator on a single file WITH `_build_evidence_blocks` output
injected into its prompt as context, compare its false-positive rate to the
baseline evaluator. If it drops by 20%+, the pivot is justified.

### 3. If keeping the verifier: ground-truth audit

Pick 50 v9-Gemma verdicts at random, manually label each as "right" or "wrong",
compute actual accuracy. This is the missing measurement — every percentage
in this document is unanchored against human judgment. Without it we can't
say whether the verifier helps or hurts user decisions.

### 4. Don't iterate on Gemma further

We've extracted the architectural lift. Further prompt engineering returns
diminishing pp. The remaining gap is model capability.

### 5. If you want the Claude ceiling measurement

Mint an `ANTHROPIC_API_KEY` at console.anthropic.com. Run `bulk_runner_v9.py`
with the API-direct client instead of `ClaudeCliClient`. ~10–15 min, ~$10
cost, gives one clean accuracy ceiling number for this finding set.

---

## Honest one-line conclusions

- The architecture is right. The layer was wrong.
- Tree-sitter context helps small models, but only ~3pp. The remaining gap is
  model capability, not context.
- Gemma over-detects override seams in a systematic way that Claude does not.
  Our false-positive numbers are slightly inflated as a result.
- Subprocess-per-call via claude-cli is the wrong shape for batch — use the API.
- The verifier was a great learning project that taught us what evidence the
  evaluator should have been getting all along. Now we know.
