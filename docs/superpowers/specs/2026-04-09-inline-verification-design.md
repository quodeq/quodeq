# Inline Verification

## Summary

Eliminate the separate verification phase by merging finding verification into the analysis phase. Files that will be analyzed get their previous findings passed as context to the analysis agent. Files that didn't change carry forward automatically. Only files that changed but are NOT in the analysis queue get a mini-verify post-analysis.

## Goals

- Reduce total API calls by ~80% for incremental evaluations
- Eliminate the 10-minute verification pool that runs before every analysis
- Maintain finding continuity (confirmed/dismissed/new)
- Simplify the pipeline from 4 phases to 3

## Pipeline change

```
BEFORE:
  Load prev → Verification pool (5 agents, 600s) → Analysis pool → Backfill → Scoring

AFTER:
  Load prev → Classify files → Analysis pool (with inline verify) → Mini-verify (if needed) → Backfill → Scoring
```

## File classification

At the start of each dimension, before launching the analysis pool, classify all files with previous findings into three buckets:

1. **Inline verify** — file is in the analysis queue AND has previous findings → pass findings as context to the analysis agent prompt
2. **Carry forward** — file has NOT changed (fingerprint match) → write findings directly to evidence JSONL, no API call
3. **Mini-verify** — file HAS changed but is NOT in the analysis queue → accumulate for post-analysis mini-verify pool

This classification reuses the existing `partition_findings_by_fingerprint()` function from `_verify_filter.py` plus a set intersection with the analysis queue files.

## Inline verification in analysis prompt

When an analysis agent takes a batch of files from the queue, and any of those files have previous findings, the prompt includes an additional section:

```
## Previous findings for files in this batch

The following findings were reported in a prior evaluation. For each file you analyze,
confirm whether these findings still apply to the current code. Report confirmed findings
alongside any new ones you discover. Dismiss findings that no longer apply.

### src/auth.py
- [violation] S-CON-3 line 42: hardcoded credentials in connection string
- [compliance] S-CON-5 line 55: proper input validation with sanitize()

### src/main.py
- [violation] P-MOD-1 line 100: function exceeds 200 lines
```

The agent reports findings as usual via MCP — confirmed previous findings are re-reported (same req ID, updated line if moved), dismissed ones are simply not reported.

## Mini-verify post-analysis

After the main analysis pool completes, check if bucket 3 (changed, not analyzed) has any files. If yes:

- Launch a mini-pool: 1-2 agents (proportional to file count), haiku model
- Timeout: 60s per 10 files, max 300s
- Uses the same verification manifest format as before
- If bucket 3 is empty, skip entirely

## Changes to `runner.py` flow

```python
def process_dimension_with_subagents(...):
    files, extensions = _list_source_files(config, dim_id)

    # Load and classify previous findings (replaces _run_verification_step)
    prev_findings = _load_and_filter_previous(config, dim_id, evidence_dir)
    carry_forward, needs_verify = partition_findings_by_fingerprint(...)
    write_carry_forward_findings(carry_forward, ...)

    # Split needs_verify into inline vs mini-verify
    queue_files = set(files)
    inline_findings = [f for f in needs_verify if f["file"] in queue_files]
    mini_verify_findings = [f for f in needs_verify if f["file"] not in queue_files]

    # Build prompt with inline findings context
    prompt = _build_subagent_prompt(config, dim_id, ctx, inline_findings)

    # Launch main analysis pool (unchanged)
    queue, results = _launch_pool(...)

    # Mini-verify only if needed
    if mini_verify_findings:
        verify_results = _dispatch_mini_verify(config, dim_id, evidence_dir, mini_verify_findings)
        results += verify_results

    return _collect_evidence(...)
```

## Files changed

| File | Change |
|------|--------|
| `subagents/runner.py:50-91` | Replace `_run_verification_step()` call with classify + inline + mini-verify flow |
| `subagents/_verification.py` | Add `_dispatch_mini_verify()` (smaller pool, proportional agents). Remove `_run_verification_step()` |
| `subagents/_prompts.py` | Accept optional `inline_findings` param, append previous findings section to prompt |
| `analysis/prompts/builder.py` | Support `previous_findings` field in `PromptContext` |

## What does NOT change

- `_verify_filter.py` — partition logic reused as-is
- `_verify_output.py` — carry forward logic reused as-is
- `_verify_io.py` — finding loading reused as-is
- `fingerprint.py` — fingerprinting reused as-is
- `file_queue.py` — queue unchanged
- `pool.py` — pool launcher unchanged
- MCP output format — agents report findings the same way
- Scoring — unchanged

## Edge cases

- **No previous findings**: classification returns all empty buckets, analysis runs as normal
- **All files unchanged**: everything carry forward, no analysis needed (existing behavior)
- **All previous findings inline**: mini-verify bucket is empty, skipped
- **No files in analysis queue**: falls back to single-agent path (existing behavior)
- **Standards changed since last run**: all findings need verification regardless of fingerprint (existing behavior in `partition_findings_by_fingerprint`)
