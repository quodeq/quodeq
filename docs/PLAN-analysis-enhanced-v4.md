# Analysis Enhanced v4 — Architecture Plan

Branch: `experimental/analysis-enhanced-v4`

## Vision

Three-tier analysis pipeline that maximizes coverage while minimizing token spend and wall-clock time. Static analysis handles the deterministic, LLM handles the judgment. **All intelligence lives in Python** — the MCP server is the control plane (routing, deduplication, enrichment). The LLM is a judgment engine that writes findings and receives work.

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
                                                      │ MCP (stdio)
                                                      ▼
                                            ┌──────────────────┐
                                            │  MCP Server (Py)  │
                                            │  ┌─────────────┐ │
                                            │  │ Router       │ │
                                            │  │ - dedup vs   │ │
                                            │  │   static     │ │
                                            │  │ - enrich     │ │
                                            │  │   req_refs   │ │
                                            │  │ - validate   │ │
                                            │  │   format     │ │
                                            │  └──────┬──────┘ │
                                            │  ┌──────▼──────┐ │
                                            │  │ Queue        │ │
                                            │  │ - prioritized│ │
                                            │  │ - file-locked│ │
                                            │  │ - shared     │ │
                                            │  └──────┬──────┘ │
                                            │  ┌──────▼──────┐ │
                                            │  │ Writer       │ │
                                            │  │ → JSONL      │ │
                                            │  └─────────────┘ │
                                            └──────────────────┘
                                                      │
                                               ┌──────▼──────┐
                                               │ Score +     │
                                               │ Report      │
                                               │ (unchanged) │
                                               └─────────────┘
```

## Core Architecture: MCP as Control Plane

The MCP server is NOT a dumb pipe. It is the **control plane** between the LLM and the data layer. The LLM calls two tools; all routing, dedup, enrichment, and writing happens in Python:

```
┌─────────────────────────────────────────────────────────┐
│  LLM (Claude CLI subagent)                               │
│                                                          │
│  reads files → judges → calls report_finding()           │
│  calls get_next_files()                                  │
│                                                          │
│  Knows NOTHING about routing, tiers, dedup, caching      │
└──────────────────┬───────────────────────────────────────┘
                   │ MCP (stdio JSON-RPC) — just transport
                   ▼
┌─────────────────────────────────────────────────────────┐
│  MCP Server (Python process)                             │
│                                                          │
│  Tools exposed:                                          │
│    report_finding(args) ──→ router.receive(finding)      │
│    get_next_files(count) ──→ queue.take(count)           │
│                                                          │
│  Router (FindingsRouter):                                │
│    1. Dedup against static findings (by file+line+req)   │
│    2. Dedup against already-seen LLM findings            │
│    3. Enrich req_refs from compiled standards             │
│    4. Validate format (required fields present)           │
│    5. Write to JSONL                                      │
│    6. Return feedback to LLM:                             │
│       - "Finding #N recorded."                            │
│       - "Already captured by static analysis. Skip."      │
│       - "Missing required field: severity"                │
│                                                          │
│  Queue (FileQueue):                                      │
│    - Shared across all subagent MCP servers               │
│    - File-locked for cross-process safety                 │
│    - Returns [] when empty → agent terminates             │
└──────────────────┬───────────────────────────────────────┘
                   │
                   ▼
             findings.jsonl
```

**Why this matters:**
- LLM tokens are expensive. Don't waste them on dedup logic or ref resolution.
- Feedback to the LLM ("already captured") saves turns — the agent moves on instead of re-reporting.
- Enrichment (req_refs) happens once in Python, not in the prompt.
- The queue is a Python data structure, not an LLM concept.

## Principles

1. **Python is the brain, LLM is the judge** — routing, dedup, enrichment, queue management all in Python
2. **Externalize evidence immediately** — findings go to JSONL via MCP, not conversation history
3. **Kill context growth** — subagents are short-lived; they write data and die
4. **Deterministic first** — static tools catch patterns; LLM catches judgment calls
5. **Same scoring pipeline** — tiers produce identical JSONL; downstream is unchanged
6. **Incremental adoption** — each phase is independently valuable and shippable

---

## Phase 1: Static Analysis Interface + SARIF Layer

**Goal:** Define a tool-agnostic static analysis interface. First implementation: Semgrep. Future: Detekt (Kotlin), ESLint (TS), Android Lint, etc. All output SARIF → convert to quodeq JSONL.

### 1.1 Static Analyzer Interface (`src/quodeq/engine/static_analysis/base.py`)

Tool-agnostic contract. Every static analyzer implements this:

```python
from abc import ABC, abstractmethod

class StaticAnalyzer(ABC):
    """Interface for static analysis tools.

    Each implementation wraps a specific tool (Semgrep, Detekt, ESLint, etc.)
    and produces SARIF output. The SARIF converter is shared — implementations
    only need to run the tool and return the SARIF path.
    """

    @abstractmethod
    def name(self) -> str:
        """Tool identifier (e.g. 'semgrep', 'detekt', 'eslint')."""

    @abstractmethod
    def supports(self, language: str) -> bool:
        """Whether this analyzer supports the given language."""

    @abstractmethod
    def run(self, repo_path: Path, dimension: str, output_dir: Path) -> Path | None:
        """Run the tool on the repo. Returns path to SARIF file, or None if tool unavailable.

        Implementations should:
        1. Check if the tool is installed (return None if not)
        2. Run with dimension-specific rules/config
        3. Write SARIF output to output_dir
        4. Return SARIF path
        """

    def is_available(self) -> bool:
        """Check if the tool binary exists on the system."""
        return shutil.which(self.name()) is not None
```

### 1.2 Analyzer Registry (`src/quodeq/engine/static_analysis/registry.py`)

Discovers and selects analyzers per language:

```python
class AnalyzerRegistry:
    """Registry of available static analyzers.

    Selects the best available tool(s) for a given language.
    Falls back gracefully — if no tool is installed, Tier 0 is skipped.
    """

    _analyzers: list[StaticAnalyzer]

    def register(self, analyzer: StaticAnalyzer): ...

    def for_language(self, language: str) -> list[StaticAnalyzer]:
        """Return all available analyzers for this language, in priority order."""

    def run_all(self, language: str, repo_path: Path, dimension: str,
                output_dir: Path) -> list[Path]:
        """Run all applicable analyzers. Returns list of SARIF paths."""
```

Priority per language (future):
| Language | Priority 1 (platform-specific) | Priority 2 (generic) |
|---|---|---|
| Kotlin/Android | Detekt, Android Lint | Semgrep |
| Java | PMD | Semgrep |
| TypeScript | ESLint/Biome | Semgrep |
| Python | Ruff, pylint | Semgrep |
| Swift/iOS | SwiftLint | Semgrep |
| Bash | ShellCheck | Semgrep |

Semgrep is the **universal fallback** — works for all languages but with shallower rules. Platform-specific tools go deeper (cyclomatic complexity, framework-aware checks, etc.).

### 1.3 Semgrep Implementation (`src/quodeq/engine/static_analysis/semgrep.py`)

First concrete implementation:

```python
class SemgrepAnalyzer(StaticAnalyzer):
    """Semgrep-based static analysis. Universal fallback for all languages."""

    def __init__(self, rules_dir: Path):
        self.rules_dir = rules_dir  # standards/semgrep/

    def name(self) -> str:
        return "semgrep"

    def supports(self, language: str) -> bool:
        return True  # Semgrep supports 30+ languages

    def run(self, repo_path: Path, dimension: str, output_dir: Path) -> Path | None:
        rules_file = self.rules_dir / f"{dimension}.yaml"
        if not rules_file.exists():
            return None
        sarif_path = output_dir / f"{dimension}_semgrep.sarif"
        subprocess.run([
            "semgrep", "scan",
            "--config", str(rules_file),
            "--sarif-output", str(sarif_path),
            "--quiet",
            str(repo_path),
        ], check=False)
        return sarif_path if sarif_path.exists() else None
```

### 1.4 Semgrep Rule Set (`standards/semgrep/`)

Per-dimension rule files. Each rule carries metadata mapping to requirement IDs:

```
standards/semgrep/
  maintainability.yaml   # M-ANA-*, M-MOD-*, M-MDF-*
  security.yaml          # S-CON-*, S-INT-*
  reliability.yaml       # R-FT-*, R-AV-*
  performance.yaml       # P-TB-*, P-RE-*
```

Example rule:
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

**What Semgrep can catch (~30-50 rules per language):**
- `!!` non-null assertions → M-ANA-10
- TODO/FIXME/HACK markers → M-ANA-13
- Hardcoded IPs, URLs, ports → M-MDF-1, S-CON-*
- Empty catch blocks → R-FT-*
- Hardcoded secrets/credentials → S-CON-*
- Unsafe casts, missing annotations

**What platform-specific tools add (future implementations):**
- Cyclomatic complexity → Detekt (M-MOD-1)
- File/function length → Detekt (M-ANA-1, M-ANA-2)
- Long parameter lists → Detekt
- Framework-specific checks → Android Lint, ESLint
- Nesting depth, coupling metrics

**What only LLM can judge (always Tier 2):**
- Architecture and design patterns
- Documentation quality/accuracy
- "Is this the right abstraction?"
- Cross-file consistency
- Context-dependent quality

### 1.5 SARIF-to-JSONL Converter (`src/quodeq/engine/static_analysis/sarif_converter.py`)

**Shared across all tools** — any analyzer that outputs SARIF gets free conversion:

```python
def convert_sarif_to_jsonl(sarif_path: Path, output_path: Path, dimension: str) -> int:
    """Convert SARIF results to quodeq JSONL format.

    Returns count of findings written.
    Works with any SARIF-producing tool (Semgrep, Detekt, ESLint, etc.).
    Rule metadata (req, principle) extracted from SARIF properties bag.
    """
```

Mapping:
| SARIF field | JSONL field |
|---|---|
| `result.ruleId` | `req` (strip tool prefix) |
| `result.level` error/warning/note | `severity` critical/major/minor |
| `result.message.text` | `reason` |
| `result.locations[0]...uri` | `file` |
| `result.locations[0]...startLine` | `line` |
| `rule.properties.principle` | `p` |
| `rule.properties.dimension` | `d` |
| hardcoded | `t` = "violation" |

### 1.6 Static Pre-Check Runner (`src/quodeq/engine/static_analysis/checks.py`)

Non-SARIF deterministic checks (pure Python, no external tools):

```python
def run_builtin_checks(repo_path: Path, dimension: str, output_path: Path,
                       language: str) -> int:
    """Run deterministic checks that don't need external tools.

    - File line counts (M-ANA-1: > 300 lines)
    - @Suppress/@SuppressWarnings counting (M-ANA-8)
    - Import counting

    Writes findings directly to quodeq JSONL format.
    Returns count of findings.
    """
```

### 1.7 Integration Point in Runner

```python
def _run_static_analysis(repo_path: Path, dimension: str, language: str,
                         evidence_dir: Path) -> Path:
    """Run Tier 0: all available static analyzers → JSONL.

    1. Run builtin checks → JSONL
    2. Query AnalyzerRegistry for available tools
    3. Run each tool → SARIF
    4. Convert all SARIF → JSONL
    5. Merge into single {dimension}_static.jsonl

    Returns path to static JSONL.
    Graceful: if no tools available, returns empty JSONL (Tier 2 handles everything).
    """
```

### 1.8 File Structure

```
src/quodeq/engine/static_analysis/
  __init__.py
  base.py              # StaticAnalyzer ABC
  registry.py          # AnalyzerRegistry
  sarif_converter.py   # SARIF → JSONL (shared)
  checks.py            # Builtin Python checks (no external tools)
  semgrep.py           # SemgrepAnalyzer (first implementation)
  # Future:
  # detekt.py          # DetektAnalyzer (Kotlin/Android)
  # eslint.py          # ESLintAnalyzer (TypeScript/JavaScript)
  # android_lint.py    # AndroidLintAnalyzer
  # ruff.py            # RuffAnalyzer (Python)
  # shellcheck.py      # ShellCheckAnalyzer (Bash)

standards/semgrep/
  maintainability.yaml
  security.yaml
  reliability.yaml
  performance.yaml
```

### Deliverable

After Phase 1: `quodeq evaluate` runs all available static analyzers first, then LLM. Interface is stable — adding Detekt or ESLint later is one new file implementing `StaticAnalyzer`. SARIF converter is shared. Builtin checks require zero external tools.

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

### 2.2 Enhanced MCP Server (`src/quodeq/engine/mcp_findings.py`)

The MCP server becomes the **control plane** with two tools and internal routing:

```python
# Two tools exposed to the LLM:

REPORT_FINDING_SCHEMA = { ... }  # existing, unchanged

GET_NEXT_FILES_SCHEMA = {
    "type": "object",
    "properties": {
        "count": {"type": "integer", "default": 5,
                   "description": "Number of files to retrieve from the analysis queue"}
    }
}
```

Internal router (invisible to LLM):

```python
class FindingsRouter:
    """Receives findings from LLM, deduplicates, enriches, writes.

    The LLM never sees this logic — it just calls report_finding()
    and gets feedback.
    """

    def __init__(self, static_findings: set, compiled_refs: dict, output: Path):
        self.seen = static_findings   # pre-loaded from Tier 0
        self.refs = compiled_refs     # pre-loaded from compiled standards
        self.fh = open(output, "a")
        self.counter = 0

    def receive(self, finding: dict) -> str:
        """Process a finding from the LLM.

        1. Dedup against static findings + already seen
        2. Enrich with req_refs from compiled standards
        3. Validate required fields
        4. Write to JSONL
        5. Return feedback to LLM
        """
        key = (finding.get("p"), finding.get("file"), finding.get("line"))
        if key in self.seen:
            return "Already captured by static analysis. Skip."
        self.seen.add(key)

        # Enrich refs — LLM doesn't need to know about this
        req = finding.get("req")
        if req and req in self.refs:
            finding["req_refs"] = self.refs[req]

        self.fh.write(json.dumps(finding) + "\n")
        self.fh.flush()
        self.counter += 1
        return f"Finding #{self.counter} recorded."
```

**Key: the "Already captured" feedback saves the LLM tokens.** It doesn't waste turns elaborating on something Semgrep already found.

The MCP server reads from the shared `FileQueue`. When queue is empty, returns `{"files": [], "done": true}` → the agent's prompt tells it to stop.

### 2.3 Subagent Spawner (`src/quodeq/engine/subagent_pool.py`)

```python
class SubagentPool:
    """Manages N parallel Claude CLI subprocesses sharing a file queue.

    Each subagent:
    - Gets the same analysis prompt + standards
    - Has its own MCP server instance (own process, shared queue)
    - MCP server handles dedup + enrichment (Python-side)
    - Writes to its own JSONL file
    - Dies when queue is empty or max_turns reached

    The queue is shared across all MCP server processes via
    file locking. Each MCP server reads from the same queue file.
    """

    def __init__(self, n_agents: int, queue: FileQueue,
                 static_findings: set, compiled_refs: dict,
                 config: AnalysisConfig):
        ...

    def run(self) -> list[Path]:
        """Launch all subagents in parallel, wait for completion.

        Each agent gets:
        - Claude CLI subprocess
        - MCP server subprocess (with FindingsRouter + FileQueue access)
        - Own JSONL output file
        - Own stream file

        Returns list of JSONL paths (one per agent).
        """

    def merge_jsonl(self, jsonl_paths: list[Path], output: Path) -> Path:
        """Concatenate and deduplicate all subagent JSONL files."""
```

### 2.4 Subagent Prompt Template (`prompts/subagent.md`)

Shorter than `compass.md` — no search strategy, no grep-first instructions. The agent receives files from the queue, not from exploration:

```markdown
# {{DIMENSION}} Analysis — Quodeq Subagent

You are analyzing **{{REPO_NAME}}** for the **{{DIMENSION}}** quality dimension.

## Your workflow

1. Call `get_next_files()` to receive files to analyze
2. Read each file using the Read tool
3. Evaluate against the standards checklist below
4. Call `report_finding()` for each violation or compliance you find
5. Repeat from step 1 until get_next_files() returns done

**Important:**
- If report_finding says "Already captured", move on — don't re-report
- Focus on issues that require judgment: architecture, design, context
- Report both violations AND compliance (balanced evaluation)

## Standards Checklist
{{STANDARDS_CHECKLIST}}
```

Note: NO `{{STATIC_FINDINGS_SUMMARY}}` needed in the prompt anymore. The MCP router handles dedup server-side. The LLM doesn't need to know what static analysis found — it just gets "Already captured" feedback if it tries to re-report. This keeps the prompt small and saves tokens.

### 2.5 Modified Runner Flow

```python
def _run_dimension_analysis_v4(self, ...):
    """Enhanced analysis: static → queue → subagents → merge."""

    # Tier 0: Static analysis (Phase 1)
    static_jsonl = _run_static_analysis(repo_path, dimension, evidence_dir, semgrep_rules)
    static_keys = _extract_finding_keys(static_jsonl)  # {(principle, file, line), ...}

    # Load compiled refs for MCP router enrichment
    compiled_refs = _build_req_refs_lookup(compiled_dir, dimension)

    # Build file queue (prioritized)
    all_files = _prescan_source_files(repo_path, plugin)
    queue = FileQueue(queue_path, _prioritize_files(all_files, static_jsonl))

    # Tier 2: Subagent pool — each MCP server gets the router
    pool = SubagentPool(
        n_agents=config.options.n_subagents or 5,
        queue=queue,
        static_findings=static_keys,
        compiled_refs=compiled_refs,
        config=analysis_config,
    )
    agent_jsonls = pool.run()

    # Merge all JSONL (static + all subagents, already deduped by router)
    merged = _merge_jsonl_files([static_jsonl] + agent_jsonls, final_jsonl_path)

    # Parse as before — unchanged
    return parse_jsonl_to_evidence(merged, context, compiled_dir)
```

### Deliverable

After Phase 2: Analysis runs 5 subagents in parallel, each pulling files from a shared queue. The MCP server deduplicates against static findings and enriches refs — all in Python, zero LLM tokens spent on that logic. Wall-clock ~10 min, covers ~150 files, uses ~6M tokens instead of ~24M.

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
| Semgrep rule quality varies by language | Start with Kotlin (GA support), expand incrementally. ~30-50 practical rules per language, not all 227 requirements. |
| Queue contention with file locking | Use atomic file operations (fcntl); fallback to pre-assigned batches if locking fails |
| API rate limits with 5 parallel agents | Make N configurable; start conservative (3); add exponential backoff |
| Subagent ignores get_next_files loop | Prompt engineering + max_turns cap as safety net; monitor stream for compliance |
| Deduplication semantic overlap | MCP router dedup by (principle, file, line); accept some overlap in differently-framed findings |
| Compliance findings drop with static-heavy pipeline | Subagent prompt explicitly asks for balanced violation+compliance; scoring adjusts |
| MCP router adds latency per finding | Router logic is <1ms Python; negligible vs ~10s LLM turn time |
| Cache invalidation correctness | Content-hash based, not timestamp; standards version + rules hash in key |
| Three tiers = three failure modes | Each tier has fallback: static fails → skip to LLM; validator fails → pass raw findings; subagent dies → remaining files stay in queue |

---

## Metrics to Track

After each phase, measure:
1. **Coverage**: files analyzed / total source files
2. **Token spend**: total input + output tokens per dimension
3. **Wall-clock time**: end-to-end per dimension
4. **Finding quality**: false positive rate (sample review)
5. **Score stability**: variance across repeated runs on same code
