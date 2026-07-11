# Quodeq accuracy benchmarks

Dev/release tooling that measures quodeq's finding accuracy against a
labeled corpus. Not shipped in the wheel. See
`docs/superpowers/specs/2026-07-10-accuracy-benchmark-harness-design.md`.

The corpus lives in the hidden directory `.corpus/` **on purpose**: its
files contain intentionally seeded violations (the answer key), and
quodeq's manifest walker skips dot-directories — so quodeq's own nightly
self-evaluation never scans the planted bugs into its own grades. The
benchmark runner copies each case into a temp workspace before evaluating,
so benchmark runs are unaffected by the hidden path.

## Run locally

```bash
PYTHONPATH=benchmarks uv run python -m quodeq_bench run \
  --corpus benchmarks/.corpus/synthetic \
  --provider ollama --model gemma4:26b-mlx \
  --n-subagents 1 \
  --out benchmarks/results/local
PYTHONPATH=benchmarks uv run python -m quodeq_bench markdown benchmarks/results/local/report.json
```

Use `--n-subagents 1` with local Ollama (it serves one request at a time —
see quodeq.env). Any provider/model quodeq supports works; the CI gate uses
the provider/model pinned in `baselines/gate.json`.

## Compare / gate

```bash
PYTHONPATH=benchmarks uv run python -m quodeq_bench compare \
  benchmarks/baselines/gate.json benchmarks/results/local/report.json --threshold 0.05
```

Exit codes: 0 ok, 1 regression, 2 errored run.

## Tests (no model calls)

```bash
uv run pytest tests/benchmarks/ -q
```

## Arming the gate

The committed `baselines/gate.json` starts as `"bootstrap": true` (compare
always passes). To arm it: take the `report.json` from a green gate run (or
a local run with the pinned model), copy its `metrics` object into
`gate.json`, remove the `bootstrap` key, and commit. When a change
legitimately improves metrics, refresh the baseline the same way in that PR.

The gate runs weekly (Saturday 12:00 UTC) on the self-hosted `quodeq`
runner with the local model pinned in `gate.json` — no cloud API key
needed. Trigger it manually any time via workflow_dispatch. Local models
are noisier than cloud ones: keep `--reps` at 2–3 and expect to widen the
threshold if the first armed weeks show false alarms.
