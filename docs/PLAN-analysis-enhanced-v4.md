# Analysis Enhanced v4 — Implementation Plan

Branch: `experimental/analysis-enhanced-v4`

## Goal

Spend less, cover more. Minimal arch changes, maximum impact.

The single biggest win: **replace one long-lived agent with N short-lived subagents**. Same MCP protocol, same JSONL, same scoring. The difference is the MCP server becomes smart (routes, deduplicates, feeds files) and the agents are disposable.

```
Current:
  1 agent × 200 turns → context grows to 500K → 50 files → ~24M tokens

Target:
  5 agents × 20 turns → context stays at 50K → 150 files → ~6M tokens
```

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│  Runner (Python) — orchestrator                             │
│                                                             │
│  1. Prescan repo → file list                                │
│  2. Build prioritized queue                                 │
│  3. Launch N subagents in parallel                          │
│  4. Wait for all to finish                                  │
│  5. Merge JSONL → existing evidence parser → score → report │
└──────┬─────────┬─────────┬─────────┬────────────────────────┘
       │         │         │         │
  ┌────▼───┐ ┌──▼────┐ ┌──▼────┐ ┌──▼────┐
  │Agent 1 │ │Agent 2│ │Agent 3│ │Agent N│  Claude CLI
  └────┬───┘ └──┬────┘ └──┬────┘ └──┬────┘  subprocesses
       │        │         │         │
  ┌────▼───┐ ┌──▼────┐ ┌──▼────┐ ┌──▼────┐
  │MCP 1   │ │MCP 2  │ │MCP 3  │ │MCP N  │  each its own process
  └────┬───┘ └──┬────┘ └──┬────┘ └──┬────┘
       │        │         │         │
       └────────┴────┬────┴─────────┘
                     │
              ┌──────▼──────────────────────┐
              │  Shared State (Python)       │
              │                              │
              │  FileQueue (file-locked)     │
              │  - prioritized file list     │
              │  - atomic take(N)            │
              │  - returns [] when empty     │
              │                              │
              │  FindingsRouter              │
              │  - dedup (file+line+req)     │
              │  - enrich req_refs           │
              │  - feedback to LLM           │
              └──────┬──────────────────────┘
                     │
                     ▼
              {dimension}_evidence.jsonl
                     │
                     ▼
              existing pipeline unchanged
              (evidence parser → scoring → report)
```

Each MCP server is its own Python process (one per agent, as today).
They share the queue and dedup set via **file-level locking** (fcntl).
Each writes to its own JSONL. Merged at the end.

## Steps

### Step 1: FileQueue (`src/quodeq/engine/file_queue.py`)

File-backed, cross-process safe queue.

```python
class FileQueue:
    """Distributes files across N subagent MCP servers.

    Backed by a JSON file. Atomic take() via fcntl file locking.
    """

    def __init__(self, queue_path: Path, files: list[str]):
        """Write initial file list to queue_path."""

    def take(self, count: int = 5) -> list[str]:
        """Atomically remove and return next N files. Returns [] when empty."""

    def remaining(self) -> int:
        """Files still in queue."""
```

No prioritization yet — just round-robin. Priority comes later as an enrichment.

**Test:** spawn 5 threads, each calling take(3). Verify no file assigned twice, all files consumed.

### Step 2: Enhanced MCP Server (`src/quodeq/engine/mcp_findings.py`)

Add `get_next_files` tool alongside existing `report_finding`. Add FindingsRouter.

Current MCP server stays as-is for the single-agent path (`--n-subagents 1` or unset). The enhanced version is used when subagent mode is active.

```python
# New tool schema
GET_NEXT_FILES_TOOL = "get_next_files"
GET_NEXT_FILES_SCHEMA = {
    "type": "object",
    "properties": {
        "count": {
            "type": "integer",
            "default": 5,
            "description": "Number of files to retrieve from the analysis queue"
        }
    }
}

# Router wraps existing write logic
class FindingsRouter:
    """Deduplicates and enriches findings before writing."""

    def __init__(self, seen_keys: set, compiled_refs: dict, output_fh: TextIO):
        self.seen = seen_keys
        self.refs = compiled_refs
        self.counter = 0
        self.fh = output_fh

    def receive(self, finding: dict) -> str:
        key = (finding.get("p"), finding.get("file"), finding.get("line"))
        if key in self.seen:
            return "Duplicate finding. Already captured."
        self.seen.add(key)

        req = finding.get("req")
        if req and req in self.refs:
            finding["req_refs"] = self.refs[req]

        self.fh.write(json.dumps(finding) + "\n")
        self.fh.flush()
        self.counter += 1
        return f"Finding #{self.counter} recorded."
```

The MCP server receives queue_path and compiled_dir as CLI args:
```
python mcp_findings.py <jsonl_file> [--queue <queue_path>] [--compiled-dir <path>]
```

When `--queue` is absent, behaves exactly as today (backwards compatible).

**Test:** mock MCP calls → verify dedup works, verify get_next_files drains queue.

### Step 3: Subagent Prompt (`prompts/subagent.md`)

Shorter than compass.md. No search strategy — the agent receives files, not explores.

```markdown
# {{DIMENSION}} Codebase Analysis — Quodeq

You are a senior software quality analyst evaluating **{{REPO_NAME}}**.

**Date:** {{DATE}}
**Dimension:** {{DIMENSION}}

## Your Workflow

1. Call `get_next_files()` to receive your next batch of files
2. Read each file using the Read tool
3. For each file, evaluate against the standards checklist below
4. Call `report_finding()` for every violation and compliance you find
5. Repeat from step 1 until get_next_files returns no more files

**Rules:**
- If report_finding says "Duplicate" or "Already captured", move on
- Report BOTH violations AND compliance (the scoring needs both)
- Call report_finding immediately after confirming each finding
- Every finding must have a specific file, line, and snippet

## Severity Definitions

- **critical** — Security vulnerability, data loss risk, or crash in production path
- **major** — Significant quality issue that should be fixed
- **minor** — Style issue, minor inefficiency, or improvement opportunity

## Standards Checklist

{{STANDARDS_CHECKLIST}}

{{ANALYSIS_GUIDANCE}}
```

**Key differences from compass.md:**
- No "grep first" strategy — files come from the queue
- No project size adaptation table — the pool handles distribution
- No "search strategy" section — just read and judge
- Includes "Duplicate" feedback handling
- Simpler, fewer tokens in prompt overhead

### Step 4: SubagentPool (`src/quodeq/engine/subagent_pool.py`)

Manages N parallel Claude CLI subprocesses.

```python
class SubagentPool:
    """Launches N subagents sharing a FileQueue.

    Each subagent:
    - Claude CLI subprocess with subagent.md prompt
    - Own MCP server process (with queue access + router)
    - Own JSONL output file
    - Own stream file
    - Dies when queue empty or max_turns hit
    """

    def __init__(self, n_agents: int, queue_path: Path,
                 prompt: str, analysis_config: AnalysisConfig,
                 compiled_dir: Path | None = None):
        ...

    def run(self) -> list[Path]:
        """Launch all agents in parallel. Block until all complete.

        Returns list of JSONL paths.
        """

    @staticmethod
    def merge_jsonl(paths: list[Path], output: Path) -> Path:
        """Concatenate JSONL files. Final dedup by (p, file, line, t)."""
```

Internally uses `concurrent.futures.ThreadPoolExecutor` or simple threading to spawn N subprocesses. Each subprocess is built with the same `_build_ai_cmd` pattern from `analysis.py`, but with:
- `subagent.md` template instead of `compass.md`
- MCP config pointing to enhanced server with `--queue` flag
- Lower `--max-turns` (30-40 instead of 200)

### Step 5: Wire into Runner

Minimal change to `runner.py`. New function alongside existing `_run_dimension_analysis`:

```python
def _run_dimension_with_subagents(
    repo_path: Path, dimension: str, prompt: str,
    evidence_dir: Path, config: AnalysisConfig,
    compiled_dir: Path | None, n_agents: int,
) -> Path:
    """Run analysis using subagent pool instead of single agent.

    1. Prescan source files
    2. Create FileQueue
    3. Build subagent prompt
    4. Launch SubagentPool
    5. Merge JSONL outputs
    6. Return merged JSONL path
    """
```

Called when `config.options.n_subagents > 1`. Otherwise falls back to existing single-agent path. **Zero changes to the existing flow when not opted in.**

### Step 6: CLI Flag

Add `--n-subagents` to CLI:

```
quodeq evaluate <repo> --n-subagents 5
```

Default: `1` (current behavior, unchanged).

---

## What Changes vs What Doesn't

| Component | Changes? | Detail |
|---|---|---|
| `mcp_findings.py` | Yes | Add get_next_files tool + FindingsRouter |
| `runner.py` | Minimal | New `_run_dimension_with_subagents` function, feature-flagged |
| `analysis.py` | No | Reuse existing `_build_ai_cmd` |
| `prompt_builder.py` | Minimal | Support loading subagent.md template |
| `evidence_parser.py` | No | Parses merged JSONL as before |
| `scoring.py` | No | Unchanged |
| `report.py` | No | Unchanged |
| `cli.py` | Minimal | Add `--n-subagents` arg |
| New files | 3 | `file_queue.py`, `subagent_pool.py`, `prompts/subagent.md` |

---

## Implementation Order

| Step | What | Depends on | Effort | Testable alone |
|---|---|---|---|---|
| 1 | FileQueue | nothing | half day | Yes (unit test) |
| 2 | Enhanced MCP server | Step 1 | 1 day | Yes (mock test) |
| 3 | Subagent prompt | nothing | half day | Yes (manual) |
| 4 | SubagentPool | Steps 1-3 | 1-2 days | Yes (integration test) |
| 5 | Runner integration | Step 4 | half day | Yes (end-to-end) |
| 6 | CLI flag | Step 5 | trivial | Yes |

**Total: ~4-5 days.**

---

## Expected Results

| Metric | Current (1 agent) | Subagents (5) |
|---|---|---|
| Files analyzed | ~50 | ~150 |
| Wall-clock per dimension | ~10 min | ~10 min |
| Total input tokens | ~24M | ~6M |
| Coverage (500-file repo) | 10% | 30% |
| Code changes | — | 3 new files, 3 modified |

---

## Future (not now, just interfaces)

These come AFTER subagents are working and measured:

| Enhancement | Approach | When |
|---|---|---|
| Static analysis (Semgrep) | `StaticAnalyzer` interface, feed static JSONL to router as pre-seen | When we want 100% file coverage |
| Haiku validator | API call between static and subagents | When false positive rate is too high |
| Git diff | `FileEnrichment` interface, skip unchanged files | When CI/CD is a use case |
| Dependency graph | `FileEnrichment` interface, fan_in for queue priority | When architectural findings matter |
| Finding cache | `FileEnrichment` interface, content-hash based | When repeat runs are common |

Each is a separate PR. Each plugs into the subagent architecture without changing it.

---

## Risks

| Risk | Mitigation |
|---|---|
| Agent ignores get_next_files loop | max_turns cap (30) as safety; prompt says "stop when done" |
| API rate limits with 5 agents | N is configurable; start with 3; add backoff |
| File lock contention on queue | fcntl is fast; queue reads are infrequent (~every 30s per agent) |
| Dedup misses semantic overlap | Accept it — same as today. Router catches exact (file, line, req) dupes |
| Agent quality drops with shorter context | Test: compare finding quality single vs subagent on same repo |
