# Finding Dismissal & False-Positive Prevention — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users permanently dismiss false-positive findings from scoring, and reduce false positives at the AI verification level with a counter-argument prompt clause.

**Architecture:** Two features: (A) prompt-level false-positive check in verification and analysis prompts — zero code changes, just text; (B) full dismissal pipeline — storage service, API routes, verification/scoring integration, and UI (dismiss button on cards, dismissed section in violations tab).

**Tech Stack:** Python/Flask backend, React frontend, JSON file storage.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/quodeq/services/dismissed.py` | Create | Read/write/remove dismissed findings from `dismissed.json` |
| `src/quodeq/api/routes_findings.py` | Create | 3 REST endpoints: list, dismiss, restore |
| `src/quodeq/api/app.py` | Modify | Register findings routes |
| `src/quodeq/analysis/subagents/_verify_pool.py` | Modify | Add false-positive clause to verification prompt |
| `src/quodeq/data/prompts/subagent.md` | Modify | Add false-positive note in Rules section |
| `src/quodeq/analysis/subagents/_verification.py` | Modify | Filter dismissed findings before verification |
| `src/quodeq/services/violations_parsing.py` | Modify | Accept and apply dismissed_keys filter |
| `src/quodeq/services/violations.py` | Modify | Load dismissed set and pass through chain |
| `src/quodeq/ui/src/api/index.js` | Modify | Add 3 API client functions |
| `src/quodeq/ui/src/features/explorer/components/EvalCards.jsx` | Modify | Add dismiss button to EvalViolationCard |
| `src/quodeq/ui/src/features/violations/components/ViolationsPage.jsx` | Modify | Add dismissed section |
| `src/quodeq/ui/src/styles/evaluation.css` | Modify | Dismissed card styles |
| `tests/services/test_dismissed.py` | Create | Unit tests for dismissed service |
| `tests/api/test_routes_findings.py` | Create | API endpoint tests |

---

### Task 1: Dismissed Findings Storage Service

**Files:**
- Create: `src/quodeq/services/dismissed.py`
- Test: `tests/services/test_dismissed.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/services/test_dismissed.py
"""Tests for the dismissed findings storage service."""
import json
from pathlib import Path

from quodeq.services.dismissed import (
    load_dismissed,
    dismiss_finding,
    restore_finding,
    dismissed_keys,
)


class TestDismissedStorage:
    def test_load_empty_when_no_file(self, tmp_path):
        result = load_dismissed(tmp_path / "nonexistent")
        assert result == []

    def test_dismiss_creates_file_and_appends(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        finding = {"req": "M-MOD-4", "file": "foo.js", "line": 4, "dimension": "maintainability", "severity": "minor"}
        dismiss_finding(project_dir, finding)
        result = load_dismissed(project_dir)
        assert len(result) == 1
        assert result[0]["req"] == "M-MOD-4"
        assert result[0]["file"] == "foo.js"
        assert result[0]["line"] == 4
        assert "dismissed_at" in result[0]

    def test_dismiss_deduplicates(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        finding = {"req": "M-MOD-4", "file": "foo.js", "line": 4, "dimension": "maintainability", "severity": "minor"}
        dismiss_finding(project_dir, finding)
        dismiss_finding(project_dir, finding)
        result = load_dismissed(project_dir)
        assert len(result) == 1

    def test_restore_removes_finding(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        dismiss_finding(project_dir, {"req": "M-MOD-4", "file": "foo.js", "line": 4, "dimension": "maintainability", "severity": "minor"})
        dismiss_finding(project_dir, {"req": "S-CON-1", "file": "bar.py", "line": 10, "dimension": "security", "severity": "major"})
        restore_finding(project_dir, {"req": "M-MOD-4", "file": "foo.js", "line": 4})
        result = load_dismissed(project_dir)
        assert len(result) == 1
        assert result[0]["req"] == "S-CON-1"

    def test_restore_nonexistent_is_noop(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        restore_finding(project_dir, {"req": "X-X-1", "file": "x.py", "line": 1})
        assert load_dismissed(project_dir) == []

    def test_dismissed_keys_returns_set_of_tuples(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        dismiss_finding(project_dir, {"req": "M-MOD-4", "file": "foo.js", "line": 4, "dimension": "maintainability", "severity": "minor"})
        keys = dismissed_keys(project_dir)
        assert keys == {("M-MOD-4", "foo.js", 4)}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/victor/GitHub/quodeq && export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/services/test_dismissed.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quodeq.services.dismissed'`

- [ ] **Step 3: Write the implementation**

```python
# src/quodeq/services/dismissed.py
"""Persistent storage for dismissed findings — per-project JSON file."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_FILENAME = "dismissed.json"


def _dismissed_path(project_dir: Path) -> Path:
    return project_dir / _FILENAME


def _key(entry: dict) -> tuple:
    return (entry.get("req", ""), entry.get("file", ""), entry.get("line", 0))


def load_dismissed(project_dir: Path) -> list[dict]:
    """Load dismissed findings for a project. Returns empty list if none."""
    path = _dismissed_path(project_dir)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def dismiss_finding(project_dir: Path, finding: dict) -> None:
    """Add a finding to the dismissed list. Deduplicates by (req, file, line)."""
    entries = load_dismissed(project_dir)
    new_key = _key(finding)
    if any(_key(e) == new_key for e in entries):
        return
    entry = {
        "req": finding.get("req", ""),
        "file": finding.get("file", ""),
        "line": finding.get("line", 0),
        "dimension": finding.get("dimension", ""),
        "severity": finding.get("severity", ""),
        "reason": finding.get("reason", ""),
        "dismissed_at": datetime.now(timezone.utc).isoformat(),
    }
    entries.append(entry)
    _dismissed_path(project_dir).write_text(
        json.dumps(entries, indent=2), encoding="utf-8",
    )


def restore_finding(project_dir: Path, finding: dict) -> None:
    """Remove a finding from the dismissed list by (req, file, line)."""
    entries = load_dismissed(project_dir)
    target = _key(finding)
    updated = [e for e in entries if _key(e) != target]
    if len(updated) == len(entries):
        return
    path = _dismissed_path(project_dir)
    if updated:
        path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
    elif path.exists():
        path.unlink()


def dismissed_keys(project_dir: Path) -> set[tuple]:
    """Return a set of (req, file, line) tuples for all dismissed findings."""
    return {_key(e) for e in load_dismissed(project_dir)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/services/test_dismissed.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/services/dismissed.py tests/services/test_dismissed.py
git commit -m "feat(dismissed): add persistent storage service for dismissed findings"
```

---

### Task 2: API Endpoints for Dismiss/Restore

**Files:**
- Create: `src/quodeq/api/routes_findings.py`
- Modify: `src/quodeq/api/app.py:174` — add `register_findings_routes(app)` call
- Test: `tests/api/test_routes_findings.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_routes_findings.py
"""Tests for the findings dismiss/restore API endpoints."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import Flask

from quodeq.api.routes_findings import register_findings_routes


@pytest.fixture()
def app(tmp_path):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["EVALUATIONS_DIR"] = str(tmp_path)
    register_findings_routes(app)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


class TestDismissEndpoint:
    def test_dismiss_creates_entry(self, client, tmp_path):
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        resp = client.post("/api/findings/dismiss", json={
            "project": "my-project",
            "req": "M-MOD-4", "file": "foo.js", "line": 4,
            "dimension": "maintainability", "severity": "minor",
            "reason": "False positive",
        })
        assert resp.status_code == 200
        data = json.loads((project_dir / "dismissed.json").read_text())
        assert len(data) == 1
        assert data[0]["req"] == "M-MOD-4"

    def test_dismiss_missing_fields_returns_400(self, client):
        resp = client.post("/api/findings/dismiss", json={"project": "x"})
        assert resp.status_code == 400


class TestRestoreEndpoint:
    def test_restore_removes_entry(self, client, tmp_path):
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        client.post("/api/findings/dismiss", json={
            "project": "my-project",
            "req": "M-MOD-4", "file": "foo.js", "line": 4,
            "dimension": "maintainability", "severity": "minor",
        })
        resp = client.post("/api/findings/restore", json={
            "project": "my-project",
            "req": "M-MOD-4", "file": "foo.js", "line": 4,
        })
        assert resp.status_code == 200
        assert not (project_dir / "dismissed.json").exists()


class TestListDismissedEndpoint:
    def test_list_returns_dismissed(self, client, tmp_path):
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        client.post("/api/findings/dismiss", json={
            "project": "my-project",
            "req": "M-MOD-4", "file": "foo.js", "line": 4,
            "dimension": "maintainability", "severity": "minor",
        })
        resp = client.get("/api/findings/dismissed?project=my-project")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1

    def test_list_empty_project(self, client):
        resp = client.get("/api/findings/dismissed?project=nonexistent")
        assert resp.status_code == 200
        assert resp.get_json() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/api/test_routes_findings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'quodeq.api.routes_findings'`

- [ ] **Step 3: Write the implementation**

```python
# src/quodeq/api/routes_findings.py
"""API routes for dismissing and restoring individual findings."""
from __future__ import annotations

from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.services.dismissed import dismiss_finding, load_dismissed, restore_finding
from quodeq.shared.utils import get_evaluations_dir


def _project_dir(project: str) -> Path:
    return Path(get_evaluations_dir()) / project


def register_findings_routes(app: Flask) -> None:
    """Register /api/findings/* routes."""

    @app.get("/api/findings/dismissed")
    def list_dismissed() -> Response:
        project = request.args.get("project", "")
        if not project:
            return jsonify([])
        return jsonify(load_dismissed(_project_dir(project)))

    @app.post("/api/findings/dismiss")
    def dismiss() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        req = body.get("req", "")
        file = body.get("file", "")
        line = body.get("line")
        if not project or not req or not file or line is None:
            return jsonify({"error": "project, req, file, and line are required"}), 400
        dismiss_finding(_project_dir(project), body)
        return jsonify({"ok": True}), 200

    @app.post("/api/findings/restore")
    def restore() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        req = body.get("req", "")
        file = body.get("file", "")
        line = body.get("line")
        if not project or not req or not file or line is None:
            return jsonify({"error": "project, req, file, and line are required"}), 400
        restore_finding(_project_dir(project), body)
        return jsonify({"ok": True}), 200
```

- [ ] **Step 4: Register routes in app factory**

In `src/quodeq/api/app.py`, add import and call:

```python
# Add to imports (around line 31)
from quodeq.api.routes_findings import register_findings_routes

# Add to _register_all_routes (around line 174, after register_standards_routes)
    register_findings_routes(app)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/api/test_routes_findings.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass (no regressions)

- [ ] **Step 7: Commit**

```bash
git add src/quodeq/api/routes_findings.py src/quodeq/api/app.py tests/api/test_routes_findings.py
git commit -m "feat(dismissed): add API endpoints for dismiss/restore/list findings"
```

---

### Task 3: Verification & Scoring Integration

**Files:**
- Modify: `src/quodeq/analysis/subagents/_verification.py:20-32` — filter dismissed findings
- Modify: `src/quodeq/services/violations_parsing.py:87-116` — accept dismissed_keys param
- Modify: `src/quodeq/services/violations.py:63-72` — load and pass dismissed set

- [ ] **Step 1: Filter dismissed findings in verification**

In `src/quodeq/analysis/subagents/_verification.py`, modify `_load_and_filter_previous` to filter dismissed findings after loading:

```python
def _load_and_filter_previous(
    config: RunConfig, dim_id: str, evidence_dir: Path,
) -> list[dict]:
    """Load previous findings and apply incremental file filter if active."""
    from quodeq.analysis.subagents.verify import load_previous_findings_for_dimension  # deferred to avoid circular import

    prev_findings = load_previous_findings_for_dimension(config, dim_id, evidence_dir)
    if not prev_findings:
        return []
    if config.options.incremental_file_filter is not None:
        filter_set = config.options.incremental_file_filter
        prev_findings = [f for f in prev_findings if f.get("file") in filter_set]

    # Filter out dismissed findings
    from quodeq.services.dismissed import dismissed_keys  # deferred to avoid import at module level
    project_dir = evidence_dir.parent
    dkeys = dismissed_keys(project_dir)
    if dkeys:
        prev_findings = [
            f for f in prev_findings
            if (f.get("p", ""), f.get("file", ""), f.get("line", 0)) not in dkeys
        ]

    return prev_findings
```

- [ ] **Step 2: Add dismissed_keys param to violations parsing**

In `src/quodeq/services/violations_parsing.py`, modify `_parse_jsonl_findings` signature and add filter:

```python
def _parse_jsonl_findings(
    lines: Iterable[str], dimension: str, req_refs_lookup: dict[str, list[dict]] | None = None,
    req_to_principle: dict[str, str] | None = None,
    dismissed_keys: set[tuple] | None = None,
) -> tuple[list[Finding], list[Finding]]:
    """Parse raw JSONL lines into deduplicated violation and compliance lists."""
    violations: list[Finding] = []
    compliance: list[Finding] = []
    seen: set[tuple] = set()
    for raw_line in lines:
        raw = raw_line.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        principle = obj.get("p") or obj.get("req")
        if not principle or obj.get("t") not in _FINDING_TYPES:
            continue
        # Skip dismissed findings
        if dismissed_keys and obj.get("t") == _TYPE_VIOLATION:
            key = (principle, obj.get("file", ""), obj.get("line", 0))
            if key in dismissed_keys:
                continue
        obj["p"] = req_to_principle.get(principle, principle) if req_to_principle else principle
        dedup_key = (principle, obj.get("t"), obj.get("file"), obj.get("line"))
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        entry = _build_finding_entry(obj, dimension, req_refs_lookup)
        if obj["t"] == _TYPE_VIOLATION:
            violations.append(entry)
        else:
            compliance.append(entry)
    return violations, compliance
```

- [ ] **Step 3: Thread dismissed set through the violations chain**

Read `parse_violations_from_jsonl` in `violations_parsing.py` to find where it calls `_parse_jsonl_findings`, and add the `dismissed_keys` parameter through. Then in `violations.py`, load the dismissed set before calling into parsing.

In `src/quodeq/services/violations.py`, modify `resolve_dimension_eval` to load and pass dismissed keys:

```python
def resolve_dimension_eval(
    base: Path, project: str, run_id: str, dimension: str,
    options: _ResolveOptions | None = None,
) -> ViolationResponse | dict[str, Any] | None:
    # ... existing code up to the jsonl_path block ...

    jsonl_path = base / "evidence" / f"{dimension}_evidence.jsonl"
    stream_path = base / "evidence" / f"{dimension}_live.stream"
    if _exists(jsonl_path) and _stat(jsonl_path).st_size > 0:
        # Load dismissed findings for this project
        from quodeq.services.dismissed import dismissed_keys as _dismissed_keys
        project_dir = base  # base is already the project run dir's parent
        # The evaluations structure is: evaluations/<project>/<run_id>/evidence/
        # base = evaluations/<project>/<run_id>, so project_dir = base.parent
        dkeys = _dismissed_keys(base.parent)
        return parse_violations_from_jsonl(
            jsonl_path, stream_path, ctx, compiled_dir=compiled_dir,
            dismissed_keys=dkeys,
        )
    # ... rest unchanged ...
```

Then thread `dismissed_keys` through `parse_violations_from_jsonl` to `_parse_jsonl_findings`. Read `parse_violations_from_jsonl` to see its signature and update it.

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/analysis/subagents/_verification.py src/quodeq/services/violations_parsing.py src/quodeq/services/violations.py
git commit -m "feat(dismissed): filter dismissed findings from verification and scoring"
```

---

### Task 4: False-Positive Counter-Argument in Prompts

**Files:**
- Modify: `src/quodeq/analysis/subagents/_verify_pool.py:25-51`
- Modify: `src/quodeq/data/prompts/subagent.md:28-35`

- [ ] **Step 1: Update verification prompt**

In `src/quodeq/analysis/subagents/_verify_pool.py`, modify `_VERIFY_PROMPT_TEMPLATE` to add a false-positive check after step 3:

```python
_VERIFY_PROMPT_TEMPLATE = """\
You are re-verifying previous evaluation findings against the current codebase.
This is a quick verification pass — be fast and decisive.

## Task

For each file in the verification manifest at `{manifest_path}`:
1. Read the file from the queue
2. Look up its findings in the manifest
3. For each finding, check if the violation/compliance condition **still applies**
   to the current code — not just whether the line exists, but whether the
   underlying issue is still present. Each finding may include a `context` field
   with ~10 lines of surrounding code that can help assess whether the violation
   still applies
4. Before confirming, check for false positives:
   - A string/number literal inside a constant, enum, or config definition is
     NOT a "magic literal" violation — the definition IS the extraction
   - A long function that only registers routes/handlers with no extractable
     logic may not be meaningfully splittable
   - Duplicated code in test fixtures may be intentional for test clarity
   - If the finding targets the fix itself (the code IS the remediation), skip it
5. If the finding still applies after the false-positive check, report it using
   the `report_finding` tool with the same fields
6. If the issue has been fixed, no longer applies, or is a false positive, skip
   it silently

## Important

- Do NOT discover new findings — only verify existing ones
- Do NOT modify any files
- Read each file, check the findings, report confirmed ones, move on
- Be fast — this should take seconds per file

Dimension: {dimension}
"""
```

- [ ] **Step 2: Update analysis prompt**

In `src/quodeq/data/prompts/subagent.md`, add after the existing Rules section (after line 35 "Skip generated, vendored, and dependency directories"):

```markdown
- **Avoid false positives** — a string/number literal inside a constant definition or enum is NOT a magic literal; a long function that only registers routes with no extractable logic is not always splittable; duplicated test setup code may be intentional. If the code IS the remediation for the issue, it is not a violation.
```

- [ ] **Step 3: Verify prompts render correctly**

Run: `uv run pytest tests/engine/test_prompt_builder.py -v`
Expected: All prompt builder tests pass

- [ ] **Step 4: Commit**

```bash
git add src/quodeq/analysis/subagents/_verify_pool.py src/quodeq/data/prompts/subagent.md
git commit -m "feat(dismissed): add false-positive counter-argument to verification and analysis prompts"
```

---

### Task 5: UI — API Client Functions

**Files:**
- Modify: `src/quodeq/ui/src/api/index.js`

- [ ] **Step 1: Add three API client functions**

Add to the end of `src/quodeq/ui/src/api/index.js` (before any default export if present):

```javascript
/**
 * List dismissed findings for a project.
 * @param {string} projectId - Project identifier
 * @returns {Promise<Array>} Dismissed findings array
 */
export async function listDismissedFindings(projectId) {
  const res = await fetch(`/api/findings/dismissed?project=${encodeURIComponent(projectId)}`);
  if (!res.ok) throw new Error(`Failed to list dismissed findings: ${res.status}`);
  return res.json();
}

/**
 * Dismiss a finding (exclude from scoring).
 * @param {string} projectId - Project identifier
 * @param {object} finding - Finding data: { req, file, line, dimension, severity, reason }
 * @returns {Promise<object>} Server response
 */
export async function dismissFinding(projectId, finding) {
  const res = await fetch('/api/findings/dismiss', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project: projectId, ...finding }),
  });
  if (!res.ok) throw new Error(`Failed to dismiss finding: ${res.status}`);
  return res.json();
}

/**
 * Restore a dismissed finding (include in scoring again).
 * @param {string} projectId - Project identifier
 * @param {object} finding - Finding key: { req, file, line }
 * @returns {Promise<object>} Server response
 */
export async function restoreFinding(projectId, finding) {
  const res = await fetch('/api/findings/restore', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project: projectId, ...finding }),
  });
  if (!res.ok) throw new Error(`Failed to restore finding: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Verify UI builds**

Run: `cd src/quodeq/ui && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add src/quodeq/ui/src/api/index.js
git commit -m "feat(dismissed): add API client functions for dismiss/restore/list"
```

---

### Task 6: UI — Dismiss Button on Violation Cards

**Files:**
- Modify: `src/quodeq/ui/src/features/explorer/components/EvalCards.jsx`
- Modify: `src/quodeq/ui/src/styles/evaluation.css`

- [ ] **Step 1: Add dismiss button to EvalViolationCard**

In `src/quodeq/ui/src/features/explorer/components/EvalCards.jsx`, modify `EvalViolationCard` to accept an `onDismiss` prop and render a dismiss button:

```jsx
export function EvalViolationCard({ v, principle, buildViolationPlanText, index, onDismiss }) {
  const { filename, ref, display } = useFileInfo(v.file, v.line, v.endLine);
  return (
    <div className={`vdetail-row vdetail-row--${v.severity}`} style={{ animationDelay: `${Math.min(index * ANIM_DELAY_PER_ITEM_MS, ANIM_MAX_DELAY_MS)}ms` }}>
      <div className="vdetail-row-main">
        <span className={`severity-tag ${v.severity}`}>{v.severity}</span>
        <span className="vrow-label">[{v.principle || principle}]</span>
        {filename && <FileCopyBtn display={display} copyText={ref} />}
        <CopyButton label="Fix plan" onClick={() => copyToClipboard(buildViolationPlanText(v))} />
        {onDismiss && (
          <button
            type="button"
            className="dismiss-btn"
            onClick={(e) => { e.stopPropagation(); onDismiss(v); }}
            title="Dismiss this finding (exclude from scoring)"
          >
            Dismiss
          </button>
        )}
      </div>
      <ViolationDetail item={v} />
    </div>
  );
}
```

- [ ] **Step 2: Add CSS for dismiss button**

In `src/quodeq/ui/src/styles/evaluation.css`, add after the `.vdetail-row-main .detail-copy-btn` block:

```css
/* Dismiss button on violation cards */
.dismiss-btn {
  font-size: 0.7rem;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  white-space: nowrap;
  transition: all 150ms ease;
}
.dismiss-btn:hover {
  color: #f0883e;
  border-color: #f0883e;
}
```

- [ ] **Step 3: Thread onDismiss through callers**

The `EvalViolationCard` is used in `EvalPrincipleDetailPage.jsx` via `ViolationListSection`. Thread the `onDismiss` callback from the page level down. The caller will need to know the project ID to call the API. Read the page component to see how `project` is available and pass `onDismiss` through.

The `onDismiss` handler at the page level should:
1. Call `dismissFinding(projectId, finding)` 
2. Remove the finding from the local violations state (optimistic update)

- [ ] **Step 4: Verify UI builds**

Run: `cd src/quodeq/ui && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/ui/src/features/explorer/components/EvalCards.jsx src/quodeq/ui/src/styles/evaluation.css
git commit -m "feat(dismissed): add dismiss button to violation cards"
```

---

### Task 7: UI — Dismissed Section in Violations Tab

**Files:**
- Modify: `src/quodeq/ui/src/features/violations/components/ViolationsPage.jsx`
- Modify: `src/quodeq/ui/src/styles/evaluation.css`

- [ ] **Step 1: Add DismissedSection component**

Create a `DismissedSection` component inside `ViolationsPage.jsx` (or a new file if the page gets too long):

```jsx
function DismissedSection({ dismissed, onRestore }) {
  const [open, setOpen] = useState(false);
  if (dismissed.length === 0) return null;
  return (
    <>
      <div className="dismissed-bar" onClick={() => setOpen((v) => !v)} role="button" tabIndex={0}>
        <span className={`dismissed-bar-icon${open ? ' open' : ''}`}>›</span>
        <span className="dismissed-bar-label">Dismissed findings</span>
        <span className="dismissed-bar-count">{dismissed.length}</span>
        <span className="dismissed-bar-note">Not included in scoring</span>
      </div>
      {open && (
        <div className="dismissed-list-inner">
          {dismissed.map((d, i) => (
            <div key={`${d.req}-${d.file}-${d.line}`} className="dismissed-card">
              <div className="dismissed-card-body">
                <div className="dismissed-card-top">
                  <span className="dismissed-tag">dismissed</span>
                  <span className="dismissed-label">[{d.dimension}]</span>
                  <span className="dismissed-file">{d.file}:{d.line}</span>
                </div>
                {d.reason && <div className="dismissed-reason">{d.reason}</div>}
              </div>
              <button type="button" className="restore-btn" onClick={() => onRestore(d)}>
                Restore
              </button>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 2: Load dismissed findings in ViolationsPage**

In the `ViolationsPage` default export, add state and effect to load dismissed findings:

```jsx
// At the top of ViolationsPage component:
const [dismissed, setDismissed] = useState([]);

useEffect(() => {
  // data.accumulated should contain the project name
  const project = data.accumulated?.project;
  if (project) {
    listDismissedFindings(project).then(setDismissed).catch(() => setDismissed([]));
  }
}, [data.accumulated?.project]);

const handleRestore = useCallback(async (finding) => {
  const project = data.accumulated?.project;
  if (!project) return;
  await restoreFinding(project, finding);
  setDismissed((prev) => prev.filter((d) => !(d.req === finding.req && d.file === finding.file && d.line === finding.line)));
}, [data.accumulated?.project]);
```

Add `<DismissedSection dismissed={dismissed} onRestore={handleRestore} />` at the bottom of the return JSX.

- [ ] **Step 3: Add CSS for dismissed section**

In `src/quodeq/ui/src/styles/evaluation.css`, add the dismissed section styles (dismissed-bar, dismissed-card, dismissed-tag, restore-btn, etc.) matching the mockup. Use the CSS from the mockup HTML as reference.

- [ ] **Step 4: Verify UI builds**

Run: `cd src/quodeq/ui && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/ui/src/features/violations/components/ViolationsPage.jsx src/quodeq/ui/src/styles/evaluation.css
git commit -m "feat(dismissed): add dismissed findings section to violations tab"
```

---

### Task 8: Integration Test & Smoke Test

**Files:**
- No new files — run existing tests and manual verification

- [ ] **Step 1: Run full Python test suite**

Run: `cd /Users/victor/GitHub/quodeq && export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/ -x -q`
Expected: All tests pass

- [ ] **Step 2: Build UI**

Run: `cd src/quodeq/ui && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Smoke test in browser**

Run: `cd /Users/victor/GitHub/quodeq && export PATH="$HOME/.local/bin:$PATH" && uv run quodeq dashboard`

Verify:
1. Open a project with violations
2. Navigate to a dimension → principle → see violation cards with "Dismiss" button
3. Click Dismiss — card disappears
4. Go to Violations tab — see "Dismissed findings (1)" at the bottom
5. Expand it — see the dismissed card with "Restore" button
6. Click Restore — card disappears from dismissed, reappears on next page load

- [ ] **Step 4: Final commit (if any fixes needed)**

```bash
git add -u
git commit -m "fix(dismissed): integration fixes from smoke test"
```
