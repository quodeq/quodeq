# Incremental Analysis (Diff-Based Re-evaluation)

**Date:** 2026-03-22
**Status:** Draft — implementation plan pending

**Dependencies:**
- `feat/token-optimization` branch (PR #107) — consolidated mode, `process_consolidated_dimensions`
- File prioritization branch (Features 1+2) — import graph infrastructure reused for dependency cascade

## Problem

When re-evaluating a project, the current system analyzes all files from scratch — even if only 50 out of 4000 changed. For repeat evaluations (the common case in CI/CD or active development), this wastes 95%+ of tokens re-reading unchanged files that will produce the same findings.

## Core Idea

On re-evaluation, determine which files changed since the last run. Only send changed files (and their dependents) to the AI agents. Carry forward cached findings for all unchanged files. Merge both into the final Evidence.

## Evaluation Fingerprint (Per-Dimension)

Each dimension stores its own fingerprint independently. A project evaluated for security and reliability has two separate fingerprints. Re-evaluating security uses the security fingerprint; evaluating a never-before-evaluated dimension (e.g., performance) runs a full analysis for that dimension regardless of other dimensions' cache state.

**`{dimension}_fingerprint.json`** (in the run's evidence directory):
```json
{
  "dimension": "security",
  "git_commit": "abc123def",
  "file_hashes": {
    "src/auth.py": "sha256:...",
    "src/routes.py": "sha256:...",
    ...
  },
  "standards_checksum": "sha256:...",
  "timestamp": "2026-03-22T20:00:00Z"
}
```

- **Git commit**: primary diff mechanism when available
- **File hashes**: fallback for non-git repos, and for verifying git diff accuracy (handles rebases/force-pushes)
- **Standards checksum**: hash of the compiled standards JSON **for this dimension** — if security standards change, only security needs full re-analysis

**Open design question**: File hashing 4K files means reading every file's content (~10-30s). Consider using `mtime + size` as a fast fingerprint, only falling back to content hash when ambiguous. To be decided during implementation planning.

## Multi-Dimension Behavior

| Scenario | Security | Reliability |
|----------|----------|-------------|
| Both previously evaluated, re-evaluating both | Incremental | Incremental |
| Only security evaluated, now evaluating both | Incremental | **Full** (no cache) |
| Both evaluated, standards changed for security only | **Full** | Incremental |
| Consolidated mode, both previously evaluated | Incremental for both (changed files union across both dimensions) |

**Consolidated mode specifics**: When evaluating multiple dimensions in one pass, the changed-file set is the **union** of changed files across all selected dimensions. A file is "unchanged" only if it was unchanged for *every* selected dimension. Carried-forward findings are loaded per-dimension from their respective previous JSONLs.

## Change Detection

On a new evaluation, compare against the most recent previous fingerprint:

1. **If git available and commit exists**: `git diff --name-only <prev_commit>..HEAD` → changed files. Fast (milliseconds).
2. **If git unavailable or commit missing**: compare file hashes — rehash all files, diff against stored hashes. Slower but reliable.
3. **If no previous fingerprint exists**: full analysis (first run).
4. **If standards checksum changed**: full analysis (rules changed, all findings potentially invalid).

## File Classification

After change detection, classify every source file into one of three buckets:

| Bucket | Action | Source |
|--------|--------|--------|
| **Changed** | Re-analyze fully | git diff or hash comparison |
| **Dependent** | Re-analyze fully | Import graph: files that import a changed file (1 level deep) |
| **Unchanged** | Carry forward findings | Everything else |

The import graph from the file prioritization feature (Layer 3: fan-in) is reused here — computed once, used for both prioritization and dependency cascade.

## Findings Cache & Carry-Forward

For unchanged files:
1. Load previous run's JSONL evidence
2. Filter to findings whose `file` is in the unchanged set
3. Copy these findings directly into the new run's JSONL (before agents start)
4. These findings appear on the dashboard immediately — no AI cost

For changed + dependent files:
1. Feed them to the file queue (prioritized per file prioritization feature)
2. AI agents analyze them normally
3. New findings are written via MCP as usual

After agents finish:
1. Merge: carried-forward findings + new findings = complete evidence
2. Deduplicate (existing dedup logic handles this)

## Cache Invalidation Rules

Carry-forward findings are invalidated (file moves to "changed" bucket) when:
- The file itself changed (content hash differs)
- A direct import dependency changed (1 level deep — not transitive, to keep it bounded)
- The compiled standards changed (standards checksum differs → full re-analysis)

**Not invalidated by**:
- Changes to unrelated files
- Changes to test files (tests don't cascade)
- Time alone (findings don't expire)

## Interaction with Verification

The existing verification pool re-checks previous findings against current code. With incremental analysis:
- **Unchanged files**: skip verification entirely — findings are known-good
- **Changed files**: verification is redundant since we're doing full re-analysis
- **Net effect**: verification pool can be skipped entirely in incremental mode, saving even more tokens

## UI Integration

- **Web dashboard**: "Re-scan changes" button alongside the existing "Run evaluation" button
- **CLI**: `--incremental` flag (default off for backward compat; could become default later)
- **API**: `incremental: true` in evaluation payload
- **Dashboard display**: show which findings are "cached" vs "new" — e.g., a subtle indicator or separate count

## Files Changed

**New files:**
- `src/quodeq/analysis/fingerprint.py` — build/compare/store evaluation fingerprints
- `src/quodeq/analysis/incremental.py` — change detection, file classification, findings carry-forward

**Modified files:**
- `src/quodeq/analysis/runner.py` — incremental path in `_run_dimensions`: detect changes, carry forward, analyze only changed files
- `src/quodeq/analysis/subagents/runner.py` — accept filtered file list (changed + dependents only)
- `src/quodeq/cli_parser.py` — add `--incremental` flag
- `src/quodeq/cli.py` — wire flag
- `src/quodeq/analysis/runner.py` — `AnalysisOptions` gets `incremental: bool = False`
- `src/quodeq/api/routes.py` — accept `incremental` from payload
- `src/quodeq/services/base.py` — `EvaluationOptions` gets `incremental: bool = False`
- Web UI: add "Re-scan changes" button

## Expected Impact

| Scenario | Full Analysis | Incremental |
|----------|--------------|-------------|
| 4000 files, 50 changed, 1 dim | 80 sessions | **1-2 sessions** |
| 4000 files, 50 changed, 6 dims | 80 sessions | **1-2 sessions** |
| 4000 files, 500 changed, 6 dims | 80 sessions | **~12 sessions** |
| First evaluation (no cache) | 80 sessions | 80 sessions (falls back to full) |

Token savings on repeat evaluations: **90-98%** for typical development cycles.

## Testing

- Unit test: fingerprint generation (git commit + file hashes + standards checksum)
- Unit test: change detection via git diff
- Unit test: change detection via hash comparison (no git)
- Unit test: dependency cascade — changed file's importers classified as "dependent"
- Unit test: unchanged file findings carried forward correctly
- Unit test: standards checksum change triggers full re-analysis
- Unit test: first run (no previous fingerprint) falls back to full analysis
- Unit test: merge of carried-forward + new findings with deduplication
- Integration test: 100 files, change 5, verify only ~5-10 analyzed

## Risks

| Risk | Mitigation |
|------|------------|
| Stale cache: carried-forward findings reference code that semantically changed but file hash is same | Extremely rare (same hash = same content). Not possible with content-based hashing |
| Dependency cascade misses indirect effects | Limited to 1-level deep intentionally; transitive cascade is unbounded. Worst case: a finding is stale until next full evaluation |
| First incremental run slow due to fingerprint generation | File hashing is fast (~1s for 4K files). Git commit is instant. One-time cost |
| User expects incremental to catch everything | UI should clearly label "incremental" vs "full" scan, with option to force full re-evaluation |
