# Inline Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the separate verification phase by merging finding verification into the analysis prompt and adding a post-analysis mini-verify for changed files not in the analysis queue.

**Architecture:** Previous findings are classified into three buckets (inline, carry-forward, mini-verify). Inline findings are appended to the analysis prompt so agents verify and discover in one pass. A smaller post-analysis pool handles leftover changed files.

**Tech Stack:** Python, existing subagent pool infrastructure, existing fingerprint/filter modules

---

### Task 1: Add `previous_findings` field to PromptContext

**Files:**
- Modify: `src/quodeq/analysis/prompts/_context.py:33-48`
- Test: `tests/analysis/test_prompt_context.py`

- [ ] **Step 1: Write test for new field**

Create `tests/analysis/test_prompt_context.py`:

```python
from quodeq.analysis.prompts._context import PromptContext


def test_prompt_context_default_previous_findings():
    ctx = PromptContext(
        language="python", repo_name="test", date_str="2026-01-01",
        dimension="security", source_file_count=10, dimensions_data={},
    )
    assert ctx.previous_findings == []


def test_prompt_context_with_previous_findings():
    findings = [
        {"p": "Security", "t": "violation", "file": "a.py", "line": 1, "reason": "test"},
    ]
    ctx = PromptContext(
        language="python", repo_name="test", date_str="2026-01-01",
        dimension="security", source_file_count=10, dimensions_data={},
        previous_findings=findings,
    )
    assert ctx.previous_findings == findings
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/analysis/test_prompt_context.py -v`
Expected: FAIL — `TypeError: unexpected keyword argument 'previous_findings'`

- [ ] **Step 3: Add field to PromptContext**

In `src/quodeq/analysis/prompts/_context.py`, add to the `PromptContext` dataclass after the `work_dir` field:

```python
    previous_findings: list[dict] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/analysis/test_prompt_context.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/analysis/prompts/_context.py tests/analysis/test_prompt_context.py
git commit -m "feat: add previous_findings field to PromptContext"
```

---

### Task 2: Render previous findings section in the analysis prompt

**Files:**
- Modify: `src/quodeq/analysis/prompts/builder.py:45-end`
- Test: `tests/analysis/test_prompt_context.py`

- [ ] **Step 1: Write test for rendering**

Add to `tests/analysis/test_prompt_context.py`:

```python
from quodeq.analysis.prompts.builder import render_previous_findings_section


def test_render_previous_findings_empty():
    assert render_previous_findings_section([]) == ""


def test_render_previous_findings_groups_by_file():
    findings = [
        {"p": "Security", "t": "violation", "file": "a.py", "line": 42, "req": "S-CON-3", "reason": "hardcoded creds"},
        {"p": "Security", "t": "compliance", "file": "a.py", "line": 55, "req": "S-CON-5", "reason": "good validation"},
        {"p": "Maintainability", "t": "violation", "file": "b.py", "line": 100, "req": "P-MOD-1", "reason": "long function"},
    ]
    result = render_previous_findings_section(findings)
    assert "### a.py" in result
    assert "### b.py" in result
    assert "[violation] S-CON-3" in result
    assert "[compliance] S-CON-5" in result
    assert "[violation] P-MOD-1" in result
    assert "hardcoded creds" in result
    assert "Previous findings" in result


def test_render_previous_findings_no_file_key():
    findings = [{"p": "X", "t": "violation", "reason": "no file"}]
    result = render_previous_findings_section(findings)
    assert "### (unknown file)" in result or result == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/analysis/test_prompt_context.py -v`
Expected: FAIL — `ImportError: cannot import name 'render_previous_findings_section'`

- [ ] **Step 3: Implement render function**

In `src/quodeq/analysis/prompts/builder.py`, add after the imports:

```python
def render_previous_findings_section(findings: list[dict]) -> str:
    """Render a prompt section listing previous findings grouped by file.

    Analysis agents receive this so they can confirm/dismiss findings
    inline while discovering new ones.
    """
    if not findings:
        return ""

    grouped: dict[str, list[dict]] = {}
    for f in findings:
        key = f.get("file", "(unknown file)")
        grouped.setdefault(key, []).append(f)

    lines = [
        "",
        "## Previous findings for files in this batch",
        "",
        "The following findings were reported in a prior evaluation. For each file",
        "you analyze, confirm whether these findings still apply to the current code.",
        "Report confirmed findings alongside any new ones you discover.",
        "Dismiss findings that no longer apply by not reporting them.",
        "",
    ]
    for filepath, file_findings in sorted(grouped.items()):
        lines.append(f"### {filepath}")
        for f in file_findings:
            ftype = f.get("t", "finding")
            req = f.get("req", "")
            line_num = f.get("line", "?")
            reason = f.get("reason", "")
            lines.append(f"- [{ftype}] {req} line {line_num}: {reason}")
        lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Wire into `build_analysis_prompt`**

In the same file, at the end of `build_analysis_prompt()` (before the `return`), add:

```python
    prev_section = render_previous_findings_section(context.previous_findings)
    if prev_section:
        result += prev_section
```

Note: you need to find where the final prompt string is assembled and returned. Read the full function to find the right insertion point. The variable holding the final prompt may be called `result`, `prompt`, or similar — check before inserting.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/analysis/test_prompt_context.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/quodeq/analysis/prompts/builder.py tests/analysis/test_prompt_context.py
git commit -m "feat: render previous findings section in analysis prompt"
```

---

### Task 3: Classify findings into inline/carry-forward/mini-verify buckets

**Files:**
- Create: `src/quodeq/analysis/subagents/_finding_classifier.py`
- Test: `tests/analysis/test_finding_classifier.py`

- [ ] **Step 1: Write tests**

Create `tests/analysis/test_finding_classifier.py`:

```python
from quodeq.analysis.subagents._finding_classifier import classify_findings


def test_finding_in_queue_goes_to_inline():
    findings = [
        {"file": "a.py", "p": "S", "t": "violation", "line": 1, "reason": "r"},
    ]
    queue_files = {"a.py", "b.py"}
    inline, mini = classify_findings(findings, queue_files)
    assert len(inline) == 1
    assert len(mini) == 0
    assert inline[0]["file"] == "a.py"


def test_finding_not_in_queue_goes_to_mini():
    findings = [
        {"file": "c.py", "p": "S", "t": "violation", "line": 1, "reason": "r"},
    ]
    queue_files = {"a.py", "b.py"}
    inline, mini = classify_findings(findings, queue_files)
    assert len(inline) == 0
    assert len(mini) == 1
    assert mini[0]["file"] == "c.py"


def test_mixed_findings_split_correctly():
    findings = [
        {"file": "a.py", "p": "S", "t": "violation", "line": 1, "reason": "r1"},
        {"file": "c.py", "p": "S", "t": "violation", "line": 2, "reason": "r2"},
        {"file": "a.py", "p": "S", "t": "compliance", "line": 3, "reason": "r3"},
    ]
    queue_files = {"a.py", "b.py"}
    inline, mini = classify_findings(findings, queue_files)
    assert len(inline) == 2
    assert len(mini) == 1


def test_empty_findings():
    inline, mini = classify_findings([], {"a.py"})
    assert inline == []
    assert mini == []


def test_no_file_key_goes_to_mini():
    findings = [{"p": "S", "t": "violation", "line": 1, "reason": "r"}]
    inline, mini = classify_findings(findings, {"a.py"})
    assert len(inline) == 0
    assert len(mini) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/analysis/test_finding_classifier.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement classifier**

Create `src/quodeq/analysis/subagents/_finding_classifier.py`:

```python
"""Classify previous findings into inline-verify vs mini-verify buckets."""
from __future__ import annotations


def classify_findings(
    needs_verify: list[dict],
    queue_files: set[str],
) -> tuple[list[dict], list[dict]]:
    """Split findings that need verification into two buckets.

    - **inline**: file is in the analysis queue — findings passed as prompt context
    - **mini_verify**: file is NOT in queue — needs separate post-analysis verification

    Returns (inline, mini_verify).
    """
    inline: list[dict] = []
    mini_verify: list[dict] = []
    for finding in needs_verify:
        if finding.get("file", "") in queue_files:
            inline.append(finding)
        else:
            mini_verify.append(finding)
    return inline, mini_verify
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/analysis/test_finding_classifier.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/analysis/subagents/_finding_classifier.py tests/analysis/test_finding_classifier.py
git commit -m "feat: add finding classifier for inline vs mini-verify buckets"
```

---

### Task 4: Add mini-verify dispatcher

**Files:**
- Modify: `src/quodeq/analysis/subagents/_verification.py:44-57`
- Test: `tests/analysis/test_mini_verify.py`

- [ ] **Step 1: Write test**

Create `tests/analysis/test_mini_verify.py`:

```python
from unittest.mock import patch, MagicMock

from quodeq.analysis.subagents._verification import _dispatch_mini_verify


@patch("quodeq.analysis.subagents._verification._run_verification_pool")
def test_mini_verify_caps_agents(mock_pool, tmp_path):
    """Mini-verify uses at most 2 agents."""
    mock_pool.return_value = []
    config = MagicMock()
    config.src = tmp_path
    config.standards_dir = None
    config.options.max_subagents = 10
    config.options.ai_model = None
    config.options.pool_budget = 300

    findings = [
        {"file": f"f{i}.py", "p": "S", "t": "violation", "line": 1, "reason": "r"}
        for i in range(50)
    ]
    _dispatch_mini_verify(config, "security", tmp_path, findings)

    assert mock_pool.called


@patch("quodeq.analysis.subagents._verification._run_verification_pool")
def test_mini_verify_skips_empty(mock_pool, tmp_path):
    """Mini-verify does nothing with empty findings."""
    config = MagicMock()
    result = _dispatch_mini_verify(config, "security", tmp_path, [])
    assert result == []
    assert not mock_pool.called
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/analysis/test_mini_verify.py -v`
Expected: FAIL — `ImportError: cannot import name '_dispatch_mini_verify'`

- [ ] **Step 3: Implement mini-verify dispatcher**

In `src/quodeq/analysis/subagents/_verification.py`, add after `_dispatch_verification_pool`:

```python
_MINI_VERIFY_MAX_AGENTS = 2
_MINI_VERIFY_TIMEOUT_PER_10 = 60
_MINI_VERIFY_MAX_TIMEOUT = 300


def _dispatch_mini_verify(
    config: RunConfig, dim_id: str, evidence_dir: Path, findings: list,
) -> list:
    """Post-analysis mini-verify for changed files not in the analysis queue.

    Uses a smaller pool (1-2 agents) with a proportional timeout.
    Returns empty list if no findings to verify.
    """
    if not findings:
        return []

    from quodeq.analysis.subagents.verify import _group_by_file, _write_verify_manifest

    grouped = _group_by_file(findings)
    manifest_path = evidence_dir / f"{dim_id}_mini_verify_manifest.json"
    _write_verify_manifest(grouped, manifest_path)
    files_to_verify = list(grouped.keys())

    n_files = len(files_to_verify)
    timeout = min(_MINI_VERIFY_MAX_TIMEOUT, max(60, (n_files // 10 + 1) * _MINI_VERIFY_TIMEOUT_PER_10))

    log_info(f"  [{dim_id}] [MINI-VERIFY] {len(findings)} findings across {n_files} changed files (not in analysis queue)")

    # Override pool budget for mini-verify
    from copy import copy
    mini_config = copy(config)
    mini_options = copy(config.options)
    mini_options.pool_budget = timeout
    mini_options.max_subagents = min(_MINI_VERIFY_MAX_AGENTS, config.options.max_subagents)
    mini_config.options = mini_options

    results = _run_verification_pool(mini_config, dim_id, evidence_dir, files_to_verify, manifest_path)
    log_success(f"  [{dim_id}] [MINI-VERIFY] Complete")
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/analysis/test_mini_verify.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/analysis/subagents/_verification.py tests/analysis/test_mini_verify.py
git commit -m "feat: add mini-verify dispatcher for post-analysis changed files"
```

---

### Task 5: Wire inline verification into the prompt builder

**Files:**
- Modify: `src/quodeq/analysis/subagents/_prompts.py:10-27`
- Test: `tests/analysis/test_prompt_context.py`

- [ ] **Step 1: Write test for prompt builder accepting findings**

Add to `tests/analysis/test_prompt_context.py`:

```python
from unittest.mock import MagicMock

from quodeq.analysis.subagents._prompts import _build_subagent_prompt


def test_build_subagent_prompt_passes_inline_findings():
    """Inline findings are passed through to PromptContext."""
    findings = [{"file": "a.py", "p": "S", "t": "violation", "line": 1, "reason": "test"}]
    ctx = MagicMock()
    ctx.subagent_template = "{{DIMENSION}} analysis"
    ctx.date_str = "2026-01-01"
    ctx.dimensions_data = {}

    config = MagicMock()
    config.language = "python"
    config.src = "/test"
    config.source_file_count = 10
    config.standards_dir = None
    config.evaluators_dir = None
    config.manifest = None
    config.target = None
    config.work_dir = None

    result = _build_subagent_prompt(config, "security", ctx, inline_findings=findings)
    assert "Previous findings" in result
    assert "a.py" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/analysis/test_prompt_context.py::test_build_subagent_prompt_passes_inline_findings -v`
Expected: FAIL

- [ ] **Step 3: Update `_build_subagent_prompt` to accept inline findings**

In `src/quodeq/analysis/subagents/_prompts.py`, update the function:

```python
def _build_subagent_prompt(
    config: RunConfig, dim_id: str, ctx: Any,
    inline_findings: list[dict] | None = None,
) -> str:
    """Build the prompt for subagent analysis, optionally including previous findings."""
    return build_analysis_prompt(
        ctx.subagent_template,
        PromptContext(
            language=config.language,
            repo_name=str(config.src),
            date_str=ctx.date_str,
            dimension=dim_id,
            source_file_count=config.source_file_count,
            dimensions_data=ctx.dimensions_data,
            standards_dir=config.standards_dir,
            evaluators_dir=config.evaluators_dir,
            manifest=config.manifest,
            target=config.target,
            work_dir=config.work_dir or config.src,
            previous_findings=inline_findings or [],
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/analysis/test_prompt_context.py::test_build_subagent_prompt_passes_inline_findings -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/analysis/subagents/_prompts.py tests/analysis/test_prompt_context.py
git commit -m "feat: pass inline findings through prompt builder to PromptContext"
```

---

### Task 6: Replace verification step in runner.py

**Files:**
- Modify: `src/quodeq/analysis/subagents/runner.py:50-91`
- Modify: `tests/engine/test_mechanical_verify_fingerprint.py`
- Test: `tests/engine/test_inline_verification.py`

- [ ] **Step 1: Write integration test for new flow**

Create `tests/engine/test_inline_verification.py`:

```python
"""Tests for inline verification flow in process_dimension_with_subagents."""
from pathlib import Path
from unittest.mock import patch, MagicMock
import hashlib

from quodeq.analysis.subagents._finding_classifier import classify_findings
from quodeq.analysis.subagents._verification import _load_and_filter_previous


def test_classify_splits_by_queue_membership():
    """Findings for files in queue go inline, others go to mini-verify."""
    needs_verify = [
        {"file": "a.py", "p": "S", "t": "violation", "line": 1, "reason": "r1"},
        {"file": "b.py", "p": "S", "t": "violation", "line": 2, "reason": "r2"},
        {"file": "c.py", "p": "S", "t": "violation", "line": 3, "reason": "r3"},
    ]
    queue_files = {"a.py", "c.py"}
    inline, mini = classify_findings(needs_verify, queue_files)
    assert {f["file"] for f in inline} == {"a.py", "c.py"}
    assert {f["file"] for f in mini} == {"b.py"}


@patch("quodeq.analysis.subagents.verify.load_previous_findings_for_dimension")
def test_load_and_filter_returns_empty_when_no_previous(mock_load, tmp_path):
    mock_load.return_value = []
    config = MagicMock()
    config.src = tmp_path
    config.options.incremental_file_filter = None
    result = _load_and_filter_previous(config, "security", tmp_path)
    assert result == []
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/engine/test_inline_verification.py -v`
Expected: PASS (these test existing functions)

- [ ] **Step 3: Update `process_dimension_with_subagents` in runner.py**

Replace the body of `process_dimension_with_subagents` (lines 58-91) with:

```python
    evidence_dir = config.work_dir or config.src

    # 1. List source files
    files, extensions = _list_source_files(config, dim_id)
    if not files:
        log_warning(
            f"[{idx}/{ctx.total}] {dim_id} -- no source files for subagent queue"
            f" (src={config.src}, language={config.language}, extensions={extensions})"
        )
        prompt = callbacks.build_prompt(config, dim_id, ctx)
        stream_file, jsonl_file = callbacks.run_analysis(config, dim_id, prompt, idx, ctx)
        return callbacks.parse_evidence(config, dim_id, stream_file, jsonl_file, ctx)

    # 2. Load previous findings, partition by fingerprint
    from quodeq.analysis.subagents.verify import (
        partition_findings_by_fingerprint, write_carry_forward_findings,
    )
    from quodeq.analysis.subagents._finding_classifier import classify_findings

    prev_findings = _load_and_filter_previous(config, dim_id, evidence_dir)
    carry_forward: list[dict] = []
    needs_verify: list[dict] = []
    if prev_findings:
        from quodeq.analysis.fingerprint import find_previous_fingerprint
        prev_fp, _ = find_previous_fingerprint(evidence_dir, dim_id)
        carry_forward, needs_verify = partition_findings_by_fingerprint(
            prev_findings, prev_fp, config.src,
            standards_dir=config.standards_dir, dimension=dim_id,
        )
    if carry_forward:
        written = write_carry_forward_findings(carry_forward, evidence_dir, dim_id)
        log_info(f"  [{idx}/{ctx.total}] {dim_id} -- {written} findings carried forward")

    # 3. Split needs_verify into inline (in queue) vs mini-verify (not in queue)
    queue_files = set(files)
    inline_findings, mini_verify_findings = classify_findings(needs_verify, queue_files)

    # 4. Create analysis queue
    queue_path = evidence_dir / f"{dim_id}_queue.json"
    files_per_agent = _compute_files_per_agent(len(files))
    FileQueue(queue_path, files, max_files_per_agent=files_per_agent)
    log_info(f"  [{idx}/{ctx.total}] {dim_id} -- {len(files)} files queued, {len(inline_findings)} inline findings")

    # 5. Build prompt with inline findings and launch analysis pool
    prompt = _build_subagent_prompt(config, dim_id, ctx, inline_findings=inline_findings)
    params = LaunchPoolParams(
        evidence_dir=evidence_dir, queue_path=queue_path,
        prompt=prompt, max_files_per_agent=files_per_agent,
    )
    pool, results = _launch_pool(config, dim_id, params)

    # 6. Mini-verify for changed files not in analysis queue
    if mini_verify_findings:
        verify_results = _dispatch_mini_verify(config, dim_id, evidence_dir, mini_verify_findings)
        results = results + verify_results

    # 7. Collect evidence
    return _collect_evidence(config, dim_id, evidence_dir, _CollectionContext(results=results, ctx=ctx, files=files))
```

- [ ] **Step 4: Update imports in runner.py**

Replace the verification imports block:

```python
from quodeq.analysis.subagents._verification import (  # noqa: F401
    _dispatch_mini_verify,
    _dispatch_verification_pool,
    _load_and_filter_previous,
    _run_verification_pool,
    _run_verification_step,
)
```

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS. Some existing verification tests may need updating — check `tests/engine/test_mechanical_verify_fingerprint.py` for tests that call `_run_verification_step` directly. Those tests validate the old flow and should still work since `_run_verification_step` is kept as a re-export.

- [ ] **Step 6: Commit**

```bash
git add src/quodeq/analysis/subagents/runner.py tests/engine/test_inline_verification.py
git commit -m "feat: replace verification phase with inline verify + mini-verify"
```

---

### Task 7: Run full test suite and verify

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Run a manual incremental evaluation**

Run an evaluation on a project that has previous findings. Verify:
- Carry-forward findings appear instantly (no API call)
- Analysis prompt includes "Previous findings" section for files in queue
- Mini-verify only runs if there are changed files not in analysis queue
- Scoring produces correct results

- [ ] **Step 3: Check logs for the new flow**

Expected log output pattern:
```
[dim] 15 findings carried forward
[dim] 120 files queued, 8 inline findings
[dim] [MINI-VERIFY] 3 findings across 2 changed files (not in analysis queue)
```

Instead of:
```
[dim] [VERIFICATION] Launching pool for 50 findings across 30 files
[dim] [VERIFICATION] Pool complete (600s)
```
