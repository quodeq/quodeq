# Analysis Enhanced v4 — Architecture Plan

Branch: `experimental/analysis-enhanced-v4`

## Vision

Three-tier analysis pipeline that maximizes coverage while minimizing token spend and wall-clock time. Static analysis handles the deterministic, LLM handles the judgment.

```
          Tier 0              Tier 1                Tier 2
      ┌───────────┐     ┌──────────────┐     ┌──────────────────┐
      │  Static    │     │  Validator    │     │  Deep Analysis   │
      │  Analysis  │────▶│  (Haiku)      │────▶│  (Sonnet ×5)     │
      │  (Semgrep) │     │              │     │  subagents       │
      │            │     │  confirm +    │     │  queue-based     │
      │  0 tokens  │     │  enrich       │     │  context-bound   │
      │  ~30s      │     │  ~80K tokens  │     │  ~6M tokens      │
      │  100% files│     │  $0.03        │     │  $3-5            │
      └───────────┘     └──────────────┘     └──────────────────┘
                                                      │
                                               ┌──────▼──────┐
                                               │ Merge +     │
                                               │ Deduplicate │
                                               │ Score +     │
                                               │ Report      │
                                               └─────────────┘
```

## Principles

1. **Externalize evidence immediately** — findings go to JSONL via MCP, not conversation history
2. **Kill context growth** — subagents are short-lived; they write data and die
3. **Deterministic first** — static tools catch patterns; LLM catches judgment calls
4. **Same scoring pipeline** — tiers produce identical JSONL; downstream is unchanged
5. **Incremental adoption** — each phase is independently valuable and shippable

---

## Phase 1: SARIF Integration Layer

**Goal:** Run Semgrep, convert output to quodeq JSONL, feed into existing scoring.

### 1.1 Semgrep Rule Set (`standards/semgrep/`)

Create per-dimension rule files with metadata mapping to requirement IDs:

```
standards/semgrep/
  maintainability.yaml   # M-ANA-*, M-MOD-*, M-MDF-*, M-TST-*
  security.yaml          # S-CON-*, S-INT-*, S-NR-*
  reliability.yaml       # R-FT-*, R-AV-*, R-RC-*
  performance.yaml       # P-TB-*, P-RE-*, P-CE-*
```

Each rule carries metadata:
```yaml
rules:
  - id: quodeq.M-ANA-10
    languages: [kotlin, java]
    pattern-regex: '\S+!!'
    message: "Non-null assertion (!!) bypasses null safety"
    severity: WARNING
    metadata:
      req: M-ANA-10
      principle: Analyzability
      dimension: maintainability
      cwe: ["CWE-476"]
```

**What Semgrep can catch (per research):**
- `!!` non-null assertions → M-ANA-10
- TODO/FIXME/HACK markers → M-ANA-13
- Hardcoded IPs, URLs, ports → M-MDF-1, S-CON-*
- Empty catch blocks → M-ANA-10, R-FT-*
- Deprecated API usage
- Hardcoded secrets/credentials → S-CON-*
- Missing annotations
- Unsafe casts

**What needs shell/AST tooling (not Semgrep):**
- File > 300 lines → `wc -l` (M-ANA-1)
- Function > 50 lines → tree-sitter or detekt
- Cyclomatic complexity → detekt (M-MOD-1)
- Long parameter lists → detekt
- Nesting depth

**What only LLM can judge:**
- Architecture, design patterns
- Documentation quality/accuracy
- Variable naming appropriateness
- Cross-file consistency
- "Is this the right abstraction?"

### 1.2 SARIF-to-JSONL Converter (`src/quodeq/engine/sarif_converter.py`)

```python
def convert_sarif_to_jsonl(sarif_path: Path, output_path: Path, dimension: str) -> int:
    """Convert SARIF results to quodeq JSONL format.

    Returns count of findings written.
    Maps: ruleId → req (via rule metadata), level → severity,
          locations → file+line, message → reason.
    """
```

Mapping:
| SARIF field | JSONL field |
|---|---|
| `result.ruleId` | `req` (strip `quodeq.` prefix) |
| `result.level` error/warning/note | `severity` critical/major/minor |
| `result.message.text` | `reason` |
| `result.locations[0]...uri` | `file` |
| `result.locations[0]...startLine` | `line` |
| `rule.metadata.principle` | `p` |
| `rule.metadata.dimension` | `d` |
| hardcoded | `t` = "violation" |

### 1.3 Static Pre-Check Runner (`src/quodeq/engine/static_checks.py`)

Orchestrates non-Semgrep deterministic checks:

```python
def run_static_checks(repo_path: Path, dimension: str, output_path: Path) -> int:
    """Run deterministic checks that don't need Semgrep.

    - File line counts (wc -l equivalent)
    - @Suppress annotation counting
    - Import/dependency counting

    Writes findings to the same JSONL format.
    Returns count of findings.
    """
```

### 1.4 Integration Point in Runner

New function in `runner.py`:

```python
def _run_static_analysis(repo_path: Path, dimension: str, evidence_dir: Path,
                         semgrep_rules_dir: Path) -> Path:
    """Run Tier 0: static analysis → JSONL.

    1. Run Semgrep with dimension-specific rules → SARIF
    2. Run deterministic checks → JSONL
    3. Convert SARIF → JSONL
    4. Merge into single {dimension}_static.jsonl

    Returns path to static JSONL.
    """
```

Called BEFORE `_run_dimension_analysis()`. The static JSONL is later merged with LLM JSONL.

### Deliverable

After Phase 1: `quodeq evaluate` runs Semgrep first, then LLM. Both produce JSONL. Merged and scored identically. Static findings are free, 100% coverage, instant.

---

## Phase 2: Subagent Parallelization

**Goal:** Replace single long-running LLM agent with N short-lived subagents sharing a file queue.

### 2.1 File Queue (`src/quodeq/engine/file_queue.py`)

Thread-safe, file-backed queue for distributing work across subagents:

```python
class FileQueue:
    """Thread-safe file queue for subagent work distribution.

    Backed by a JSON file with file locking for cross-process safety.
    Supports priority ordering (git recency, fan-in, static finding count).
    """

    def __init__(self, queue_path: Path, files: list[dict]):
        """Initialize with prioritized file list.

        Each entry: {path: str, priority: float, static_findings: int}
        """

    def take(self, count: int = 5) -> list[str]:
        """Atomically take next N files from queue. Returns [] when empty."""

    def remaining(self) -> int:
        """Files still in queue."""
```

### 2.2 Queue MCP Tool

Extend `mcp_findings.py` with a second tool:

```python
GET_NEXT_FILES_SCHEMA = {
    "type": "object",
    "properties": {
        "count": {"type": "integer", "default": 5,
                   "description": "Number of files to retrieve from the analysis queue"}
    }
}
```

The MCP server reads from the shared `FileQueue`. When queue is empty, returns `{"files": [], "done": true}`.

Each subagent's prompt instructs:
```
1. Call get_next_files() to receive your next batch
2. Read and analyze each file against the standards
3. Call report_finding() for each finding
4. Repeat until get_next_files() returns done=true
```

### 2.3 Subagent Spawner (`src/quodeq/engine/subagent_pool.py`)

```python
class SubagentPool:
    """Manages N parallel Claude CLI subprocesses sharing a file queue.

    Each subagent:
    - Gets the same analysis prompt + standards
    - Has its own MCP server (with get_next_files + report_finding)
    - Writes to its own JSONL file
    - Dies when queue is empty or max_turns reached
    """

    def __init__(self, n_agents: int, queue: FileQueue, config: AnalysisConfig):
        ...

    def run(self) -> list[Path]:
        """Launch all subagents, wait for completion.

        Returns list of JSONL paths (one per agent).
        """

    def merge_jsonl(self, jsonl_paths: list[Path], output: Path) -> Path:
        """Concatenate and deduplicate all subagent JSONL files."""
```

### 2.4 Subagent Prompt Template (`prompts/subagent.md`)

Shorter than `compass.md` — no search strategy instructions needed:

```markdown
# {{DIMENSION}} Analysis — Quodeq Subagent

You are analyzing **{{REPO_NAME}}** for the **{{DIMENSION}}** quality dimension.

## Your workflow

1. Call `get_next_files()` to receive files to analyze
2. Read each file
3. Evaluate against the standards checklist below
4. Call `report_finding()` for each violation or compliance
5. Repeat from step 1 until no more files

## Standards Checklist
{{STANDARDS_CHECKLIST}}

## Already known (from static analysis)
{{STATIC_FINDINGS_SUMMARY}}

Focus on issues that require human judgment: architecture, design,
context-dependent quality. The static findings above are already captured.
```

Key difference: includes `{{STATIC_FINDINGS_SUMMARY}}` so subagents don't duplicate static analysis findings.

### 2.5 Modified Runner Flow

```python
def _run_dimension_analysis_v4(self, ...):
    """Enhanced analysis: static → queue → subagents → merge."""

    # Tier 0: Static analysis
    static_jsonl = _run_static_analysis(repo_path, dimension, evidence_dir, semgrep_rules)

    # Build file queue (prioritized)
    all_files = _prescan_source_files(repo_path, plugin)
    queue = FileQueue(queue_path, _prioritize_files(all_files, static_jsonl))

    # Tier 2: Subagent pool
    pool = SubagentPool(
        n_agents=config.options.n_subagents or 5,
        queue=queue,
        config=analysis_config,
    )
    agent_jsonls = pool.run()

    # Merge all JSONL (static + all subagents)
    merged = pool.merge_jsonl([static_jsonl] + agent_jsonls, final_jsonl_path)

    # Parse as before — unchanged
    return parse_jsonl_to_evidence(merged, context, compiled_dir)
```

### Deliverable

After Phase 2: Analysis runs 5 subagents in parallel, each pulling files from a shared queue. Wall-clock ~10 min, covers ~150 files, uses ~6M tokens instead of ~24M.

---

## Phase 3: Validation Layer (Haiku)

**Goal:** Fast, cheap validation pass between static analysis and deep analysis.

### 3.1 Validator (`src/quodeq/engine/validator.py`)

```python
def validate_static_findings(
    findings_jsonl: Path,
    repo_path: Path,
    model: str = "haiku",
) -> Path:
    """Validate static analysis findings with a cheap LLM pass.

    Batches findings by file. For each file:
    - Reads the relevant code
    - Sends findings + code to Haiku
    - Haiku returns: confirmed (with enriched reason) or rejected

    Writes validated findings to a new JSONL.
    Returns path to validated JSONL.
    """
```

Batch request format (sent to Haiku API directly, not via Claude CLI):
```json
{
  "file": "ArticleViewModel.kt",
  "code": "... lines 340-410 ...",
  "findings": [
    {"req": "M-MOD-1", "line": 345, "reason": "cyclomatic complexity"},
    {"req": "M-ANA-2", "line": 346, "reason": "function > 50 lines"}
  ]
}
```

Response format:
```json
{
  "validated": [
    {"req": "M-MOD-1", "line": 345, "confirmed": true, "reason": "18 branches in when-expression..."},
    {"req": "M-ANA-2", "line": 346, "confirmed": true, "reason": "Function spans lines 345-407..."}
  ]
}
```

### 3.2 Smart File Router

After validation, classify files for Tier 2:

```python
def route_files(all_files: list, static_findings: dict, validated: dict) -> dict:
    """Classify files for subagent analysis.

    Returns:
      skip: files with 0 findings AND < 100 lines (low risk)
      deep: files with complex/architectural findings OR high centrality
      normal: everything else
    """
```

Priority signals:
- Git recency (recently changed → higher priority)
- Import fan-in (many dependents → higher priority)
- Static finding density (more findings → more interesting)
- File complexity (longer files → more likely to have issues)

### Deliverable

After Phase 3: Static findings are validated before scoring. False positives filtered. Files smartly routed to subagents based on risk.

---

## Phase 4: Incremental Analysis (Cache Layer)

**Goal:** Skip unchanged files on re-runs. Massive speedup for CI/CD.

### 4.1 Finding Cache (`src/quodeq/engine/finding_cache.py`)

```python
class FindingCache:
    """Content-addressed cache for file-level findings.

    Key: sha256(file_content + standards_version + semgrep_rules_hash)
    Value: list of findings for that file

    Storage: JSON file in .quodeq/cache/findings/
    """

    def get(self, file_path: Path, standards_version: str) -> list[dict] | None:
        """Return cached findings or None if stale/missing."""

    def put(self, file_path: Path, standards_version: str, findings: list[dict]):
        """Cache findings for a file."""

    def invalidate_changed(self, repo_path: Path, since_commit: str):
        """Invalidate cache entries for files changed since commit."""
```

### 4.2 Git-Aware Diff

```python
def get_changed_files(repo_path: Path, since: str = "HEAD~1") -> set[str]:
    """Return files changed since a commit/tag."""
```

### 4.3 Integration

```python
# In the runner:
cached_findings = cache.get_all_valid(repo_path, standards_version)
changed_files = get_changed_files(repo_path, since=last_run_commit)
files_to_analyze = [f for f in all_files if f in changed_files or f not in cached_findings]
# Only queue files_to_analyze for subagents
# Merge cached + fresh findings
```

### Deliverable

After Phase 4: Re-runs on a repo with 10% changed files complete in ~1 min instead of ~10 min. CI/CD integration becomes practical.

---

## Phase 5: Cross-File Analysis

**Goal:** Catch issues that span multiple files.

### 5.1 Dependency Graph Builder

```python
def build_import_graph(repo_path: Path, language: str) -> dict:
    """Build file-level dependency graph from imports.

    Returns: {file: {imports: [files], imported_by: [files], fan_in: int}}
    Uses tree-sitter or regex per language.
    """
```

Detects:
- Circular dependencies (graph cycles)
- God modules (high fan-in)
- Orphan modules (zero fan-in, zero fan-out)
- Layer violations (presentation → data bypassing domain)

### 5.2 Architecture Subagent

A specialized subagent that receives the dependency graph + high-level summaries instead of individual files:

```
Prompt: "Here is the module dependency graph for this project.
         Identify architectural violations: circular deps, god modules,
         layer violations, missing abstractions."
```

This is a single subagent, short context, high-value findings.

### Deliverable

After Phase 5: Cross-file architectural issues detected. Fills the biggest blind spot.

---

## Implementation Order & Milestones

| Phase | Effort | Impact | Ships independently |
|---|---|---|---|
| **Phase 1**: SARIF layer | 3-4 days | +100% coverage, 0 extra tokens | Yes |
| **Phase 2**: Subagents | 4-5 days | 3x files, 4x fewer tokens | Yes |
| **Phase 3**: Validator | 2-3 days | fewer false positives, smart routing | Yes |
| **Phase 4**: Cache | 2-3 days | 10x faster re-runs | Yes |
| **Phase 5**: Cross-file | 3-4 days | architectural findings | Yes |

**Total: ~15-19 days for the full architecture.**

Each phase is a PR. Each is independently valuable. No phase depends on a later phase.

---

## Config Surface

New fields in `AnalysisOptions` / CLI args:

```
--n-subagents N        # Number of parallel subagents (default: 5)
--skip-static          # Skip Tier 0 static analysis
--skip-validation      # Skip Tier 1 Haiku validation
--no-cache             # Disable finding cache
--since COMMIT         # Only analyze files changed since commit
--max-files-per-agent  # Cap files per subagent (default: 30)
```

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Semgrep rule quality varies by language | Start with Kotlin (GA support), expand incrementally |
| Queue contention with file locking | Use atomic file operations; fallback to pre-assigned batches |
| API rate limits with 5 parallel agents | Make N configurable; start conservative; add backoff |
| Subagent prompt too short → shallow analysis | Include static findings as context; tune turns per agent |
| Deduplication edge cases | Dedup by (principle, file, line, type) — already exists |
| Cache invalidation correctness | Content-hash based, not timestamp; standards version in key |

---

## Metrics to Track

After each phase, measure:
1. **Coverage**: files analyzed / total source files
2. **Token spend**: total input + output tokens per dimension
3. **Wall-clock time**: end-to-end per dimension
4. **Finding quality**: false positive rate (sample review)
5. **Score stability**: variance across repeated runs on same code
