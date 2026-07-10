# Quodeq accuracy benchmarks

Dev/release tooling that measures quodeq's finding accuracy against a
labeled corpus. Not shipped in the wheel. See
`docs/superpowers/specs/2026-07-10-accuracy-benchmark-harness-design.md`.

## Run locally

```bash
PYTHONPATH=benchmarks uv run python -m quodeq_bench run \
  --corpus benchmarks/corpus/synthetic \
  --provider claude --model claude-haiku-4-5-20251001 \
  --out benchmarks/results/local
PYTHONPATH=benchmarks uv run python -m quodeq_bench markdown benchmarks/results/local/report.json
```

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
