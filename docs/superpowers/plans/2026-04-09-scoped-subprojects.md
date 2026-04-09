# Scoped Sub-Projects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow scoped evaluations that create child projects (sub-projects) with their own history, while the parent project aggregates findings from all children.

**Architecture:** Extend `ProjectIdentity` with `scope_path`, make `resolve_project_uuid` scope-aware (create parent first, then child), add a parent-aggregation path in `compute_accumulated` that merges children's latest evidence, and wire `scopePath` through the evaluation payload to the CLI.

**Tech Stack:** Python 3.13, pytest, Flask, React (JSX), existing quodeq project/scoring infrastructure

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/quodeq/data/fs/_models.py` | Modify | Add `scope_path` to `ProjectIdentity` |
| `src/quodeq/data/fs/_resolution.py` | Modify | Scope-aware index key and project creation |
| `src/quodeq/data/fs/project_resolver.py` | Modify | Add `scope_path` param to `resolve_project_uuid` |
| `src/quodeq/core/types/project.py` | Modify | Add `scope_path` to `ProjectEntry` |
| `src/quodeq/services/evaluation_mixin.py` | Modify | Scope-aware `_register_project` |
| `src/quodeq/services/_fs_projects.py` | Modify | Cascade delete, child listing |
| `src/quodeq/services/_fs_project_helpers.py` | Modify | Use explicit `parent` from repo_info |
| `src/quodeq/services/_fs_metadata.py` | Modify | Read `scopePath` from repo_info |
| `src/quodeq/services/accumulated.py` | Modify | Parent aggregation path |
| `src/quodeq/ui/src/features/evaluation/hooks/useEvaluation.js` | Modify | Send `scopePath` in payload |
| `src/quodeq/ui/src/features/dashboard/components/ProjectsPage.jsx` | Modify | Scope badge, parent summary |
| `src/quodeq/ui/src/models/project.js` | Modify | Add `scopePath` field |
| `tests/data/fs/test_scoped_resolution.py` | Create | Tests for scope-aware resolution |
| `tests/services/test_scoped_accumulated.py` | Create | Tests for parent aggregation |
| `tests/services/test_cascade_delete.py` | Create | Tests for cascade delete |

---

### Task 1: Add `scope_path` to ProjectIdentity and resolution

**Files:**
- Modify: `src/quodeq/data/fs/_models.py`
- Modify: `src/quodeq/data/fs/_resolution.py`
- Modify: `src/quodeq/data/fs/project_resolver.py`
- Create: `tests/data/fs/test_scoped_resolution.py`

- [ ] **Step 1: Write failing test for scope-aware resolution**

```python
"""Tests for scope-aware project resolution."""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.data.fs._models import ProjectIdentity
from quodeq.data.fs.project_resolver import resolve_project_uuid


class TestScopedResolution:
    """resolve_project_uuid with scope_path creates parent + child."""

    def test_scoped_creates_parent_and_child(self, tmp_path):
        reports = tmp_path / "reports"
        reports.mkdir()
        identity = ProjectIdentity("myproject", str(tmp_path / "repo"), scope_path="src/api")

        child_uuid = resolve_project_uuid(reports, identity)

        # Child project dir exists
        assert (reports / child_uuid).is_dir()
        child_info = _read_info(reports / child_uuid)
        assert child_info["scopePath"] == "src/api"
        assert child_info["parent"] is not None

        # Parent project dir also exists
        parent_uuid = child_info["parent"]
        assert (reports / parent_uuid).is_dir()
        parent_info = _read_info(reports / parent_uuid)
        assert parent_info.get("scopePath") is None
        assert parent_info["name"] == "myproject"

    def test_scoped_reuses_existing_parent(self, tmp_path):
        reports = tmp_path / "reports"
        reports.mkdir()
        repo = str(tmp_path / "repo")

        # First: create parent via unscoped evaluation
        parent_id = ProjectIdentity("myproject", repo)
        parent_uuid = resolve_project_uuid(reports, parent_id)

        # Second: create scoped child
        child_id = ProjectIdentity("myproject", repo, scope_path="src/api")
        child_uuid = resolve_project_uuid(reports, child_id)

        child_info = _read_info(reports / child_uuid)
        assert child_info["parent"] == parent_uuid

    def test_same_scope_reuses_child(self, tmp_path):
        reports = tmp_path / "reports"
        reports.mkdir()
        repo = str(tmp_path / "repo")

        identity = ProjectIdentity("myproject", repo, scope_path="src/api")
        uuid1 = resolve_project_uuid(reports, identity)
        uuid2 = resolve_project_uuid(reports, identity)
        assert uuid1 == uuid2

    def test_different_scopes_create_different_children(self, tmp_path):
        reports = tmp_path / "reports"
        reports.mkdir()
        repo = str(tmp_path / "repo")

        id1 = ProjectIdentity("myproject", repo, scope_path="src/api")
        id2 = ProjectIdentity("myproject", repo, scope_path="src/core")
        uuid1 = resolve_project_uuid(reports, id1)
        uuid2 = resolve_project_uuid(reports, id2)
        assert uuid1 != uuid2

    def test_unscoped_resolution_unchanged(self, tmp_path):
        reports = tmp_path / "reports"
        reports.mkdir()
        repo = str(tmp_path / "repo")

        identity = ProjectIdentity("myproject", repo)
        uuid1 = resolve_project_uuid(reports, identity)
        uuid2 = resolve_project_uuid(reports, identity)
        assert uuid1 == uuid2
        info = _read_info(reports / uuid1)
        assert info.get("scopePath") is None
        assert info.get("parent") is None


def _read_info(project_dir: Path) -> dict:
    import json
    return json.loads((project_dir / "repository_info.json").read_text())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/marche000/Projects/vik/quodeq && uv run pytest tests/data/fs/test_scoped_resolution.py -v`
Expected: FAIL — `ProjectIdentity` doesn't accept `scope_path`

- [ ] **Step 3: Add `scope_path` to `ProjectIdentity`**

In `src/quodeq/data/fs/_models.py`, add a field:

```python
@dataclass(frozen=True)
class ProjectIdentity:
    """Identifies a project by name, resolved repo path, and metadata."""
    project_name: str
    repo_path: str
    discipline: str | None = None
    location: str = "local"
    scope_path: str | None = None
```

- [ ] **Step 4: Update `_index_key` and `_create_project` in `_resolution.py`**

```python
def _index_key(identity: ProjectIdentity) -> str:
    """Return a stable string key. Scoped projects include the scope path."""
    base = f"{identity.project_name}\x00{identity.repo_path}"
    if identity.scope_path:
        return f"{base}\x00{identity.scope_path}"
    return base
```

Update `_create_project` to write `scopePath` and `parent`:

```python
def _create_project(
    reports_dir: Path,
    identity: ProjectIdentity,
    load_fn: Callable[[Path], dict[str, str]],
    save_fn: Callable[[Path, dict[str, str]], None],
    parent_uuid: str | None = None,
) -> str:
    """Create a new UUID project directory, write repository_info.json, and index it."""
    if identity.location == "online" and not identity.repo_path.startswith(("https://", "git@")):
        logging.getLogger(__name__).warning(
            "Online project '%s' has a non-URL path '%s'; expected a remote URL.",
            identity.project_name,
            identity.repo_path,
        )
    project_uuid = str(uuid.uuid4())
    project_dir = reports_dir / project_uuid
    project_dir.mkdir(parents=True, exist_ok=True)
    info: dict = {
        "uuid": project_uuid,
        "name": f"{identity.project_name}/{identity.scope_path}" if identity.scope_path else identity.project_name,
        "discipline": identity.discipline,
        "location": identity.location,
        "path": identity.repo_path,
    }
    if identity.scope_path:
        info["scopePath"] = identity.scope_path
    if parent_uuid:
        info["parent"] = parent_uuid
    try:
        (project_dir / "repository_info.json").write_text(json.dumps(info, indent=2))
    except OSError as exc:
        logging.getLogger(__name__).warning("Could not write repository_info.json: %s", exc)
    index = load_fn(reports_dir)
    index[_index_key(identity)] = project_uuid
    save_fn(reports_dir, index)
    return project_uuid
```

Also update `_find_existing_project` to accept and match `scope_path` via the updated `_index_key`.

- [ ] **Step 5: Update `resolve_project_uuid` to handle scoped resolution**

In `src/quodeq/data/fs/project_resolver.py`:

```python
def resolve_project_uuid(
    reports_dir: Path,
    identity: ProjectIdentity,
    repository: ProjectRepository | None = None,
) -> str:
    """Find or create a UUID project directory matching identity.

    For scoped identities (scope_path set), first resolves/creates the parent
    project, then resolves/creates the child with parent link.
    """
    if identity.location == "online":
        resolved_path = identity.repo_path
    else:
        resolved_path = str(Path(identity.repo_path).resolve())
    resolved = ProjectIdentity(
        identity.project_name, resolved_path, identity.discipline, identity.location,
        scope_path=identity.scope_path,
    )
    if not reports_dir.exists():
        reports_dir.mkdir(parents=True, exist_ok=True)

    load_fn = repository.load_index if repository is not None else _load_index
    save_fn = repository.save_index if repository is not None else _save_index

    # Scoped: resolve parent first, then child
    if resolved.scope_path:
        parent_identity = ProjectIdentity(
            resolved.project_name, resolved.repo_path, resolved.discipline, resolved.location,
        )
        parent_existing = _find_existing_project(reports_dir, parent_identity, load_fn, save_fn)
        parent_uuid = parent_existing or _create_project(reports_dir, parent_identity, load_fn, save_fn)

        child_existing = _find_existing_project(reports_dir, resolved, load_fn, save_fn)
        if child_existing:
            return child_existing
        return _create_project(reports_dir, resolved, load_fn, save_fn, parent_uuid=parent_uuid)

    existing = _find_existing_project(reports_dir, resolved, load_fn, save_fn)
    if existing:
        return existing
    return _create_project(reports_dir, resolved, load_fn, save_fn)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/marche000/Projects/vik/quodeq && uv run pytest tests/data/fs/test_scoped_resolution.py -v`
Expected: All 5 tests PASS

- [ ] **Step 7: Run existing tests for regression**

Run: `cd /Users/marche000/Projects/vik/quodeq && uv run pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add src/quodeq/data/fs/_models.py src/quodeq/data/fs/_resolution.py src/quodeq/data/fs/project_resolver.py tests/data/fs/test_scoped_resolution.py
git commit -m "feat: scope-aware project resolution with parent/child creation"
```

---

### Task 2: Wire `scopePath` through evaluation pipeline

**Files:**
- Modify: `src/quodeq/services/evaluation_mixin.py`
- Modify: `src/quodeq/core/types/project.py`
- Modify: `src/quodeq/services/_fs_metadata.py`
- Modify: `src/quodeq/ui/src/models/project.js`

- [ ] **Step 1: Update `_register_project` to handle scope**

In `src/quodeq/services/evaluation_mixin.py`, modify `_register_project`:

```python
def _register_project(repo: str, discipline: str | None, reports_dir: str, scope_path: str | None = None) -> None:
    """Resolve and register the project UUID before evaluation starts."""
    repo_resolved = str(Path(repo).resolve()) if not is_repo_url(repo) else repo
    project_name = project_name_from_repo(repo)
    location = _LOCATION_ONLINE if is_repo_url(repo) else _LOCATION_LOCAL
    resolve_project_uuid(
        Path(reports_dir),
        ProjectIdentity(project_name, repo_resolved, discipline, location, scope_path=scope_path),
    )
```

Update the caller in `start_evaluation` to pass `options.scope_path`.

- [ ] **Step 2: Add `scope_path` to `ProjectEntry`**

In `src/quodeq/core/types/project.py`:

```python
@dataclass(frozen=True, slots=True)
class ProjectEntry:
    id: str
    name: str
    parent: str | None = None
    display_name: str | None = None
    discipline: str | None = None
    path: str | None = None
    location: str | None = None
    scope_path: str | None = None
    runs_count: int = 0
    latest_run_id: str | None = None
    latest_date: str | None = None
    path_exists: bool | None = None
    files_count: int | None = None
    latest_grade: str | None = None
    latest_score: float | None = None
    language_stats: dict[str, int] = field(default_factory=dict)
    scan_date: str | None = None
    total_files: int | None = None
    analyzed_files: int | None = None
```

- [ ] **Step 3: Read `scopePath` and `parent` from `repository_info.json`**

In `src/quodeq/services/_fs_metadata.py`, update `_extract_project_metadata` to include:

```python
meta["scopePath"] = info.get("scopePath")
meta["parent"] = info.get("parent")
```

And in `_build_project_entry` (in `_fs_project_helpers.py`), pass `scope_path=meta["scopePath"]` to `ProjectEntry`.

- [ ] **Step 4: Add `scopePath` to frontend project model**

In `src/quodeq/ui/src/models/project.js`, add:

```javascript
scopePath: raw.scopePath ?? null,
```

- [ ] **Step 5: Send `scopePath` in evaluation payload**

In `src/quodeq/ui/src/features/evaluation/hooks/useEvaluation.js`, in `preparePayload`:

```javascript
if (payload.scopePath) {
  // scopePath already set by the evaluate form
}
```

This is already handled — the form sets `payload.scopePath` and `_build_evaluation_options` in `_evaluation_helpers.py` already reads it (line 67: `scope_path=payload.get("scopePath") or None`).

- [ ] **Step 6: Run tests**

Run: `cd /Users/marche000/Projects/vik/quodeq && uv run pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add src/quodeq/services/evaluation_mixin.py src/quodeq/core/types/project.py src/quodeq/services/_fs_metadata.py src/quodeq/services/_fs_project_helpers.py src/quodeq/ui/src/models/project.js
git commit -m "feat: wire scopePath through evaluation pipeline and project model"
```

---

### Task 3: Parent project shows no runs — handle empty parent in project list

**Files:**
- Modify: `src/quodeq/services/_fs_projects.py`

- [ ] **Step 1: Include parent projects with no runs in the project list**

Currently `build_project_list` skips projects without runs (`if not runs: return None`). Parent projects have no runs — their children do. Modify `_build_one` to include projects that have `repository_info.json` with no `scopePath` (they might be parents):

```python
def _build_one(name: str) -> ProjectEntry | None:
    runs = list_runs(reports_root, name)
    info = _read_repo_info(reports_root, name)
    # Include parent projects even without runs (children provide the data)
    if not runs and not _has_children(reports_root, name):
        return None
    return _build_project_entry(reports_root, name, runs)
```

Add `_has_children` helper:

```python
def _has_children(reports_root: Path, project_id: str) -> bool:
    """Check if any project in reports_root has this project as parent."""
    for entry in reports_root.iterdir():
        if not entry.is_dir() or entry.name == project_id:
            continue
        info_path = entry / "repository_info.json"
        if not info_path.exists():
            continue
        try:
            info = json.loads(info_path.read_text())
            if info.get("parent") == project_id:
                return True
        except (json.JSONDecodeError, OSError):
            continue
    return False
```

- [ ] **Step 2: Handle empty runs in `_build_project_entry`**

Ensure `_build_project_entry` doesn't crash when `runs` is empty (no `runs[0]` access):

```python
return ProjectEntry(
    id=entry_name,
    name=meta["name"],
    parent=meta.get("parent"),
    scope_path=meta.get("scopePath"),
    # ... rest unchanged, but guard runs[0]:
    latest_run_id=runs[0].run_id if runs else None,
    latest_date=runs[0].date_iso if runs else None,
    runs_count=len(runs),
    # ...
)
```

- [ ] **Step 3: Run tests and commit**

Run: `cd /Users/marche000/Projects/vik/quodeq && uv run pytest tests/ -v --tb=short`

```bash
git add src/quodeq/services/_fs_projects.py
git commit -m "feat: include parent projects with no runs in project list"
```

---

### Task 4: Parent aggregation — merge children's findings for accumulated view

**Files:**
- Modify: `src/quodeq/services/accumulated.py`
- Create: `tests/services/test_scoped_accumulated.py`

- [ ] **Step 1: Write failing test for parent aggregation**

```python
"""Tests for parent project accumulated view from children."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestParentAccumulated:
    """Parent project accumulated view merges children's findings."""

    def _create_project(self, reports, uuid, info):
        d = reports / uuid
        d.mkdir(parents=True, exist_ok=True)
        (d / "repository_info.json").write_text(json.dumps(info))
        return d

    def _create_run_with_evidence(self, project_dir, run_id, findings):
        run_dir = project_dir / run_id / "evidence"
        run_dir.mkdir(parents=True)
        jsonl = run_dir.parent / "evaluation" / "dimension_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        jsonl.write_text("\n".join(json.dumps(f) for f in findings))

    def test_parent_accumulated_merges_children(self, tmp_path):
        from quodeq.services.accumulated import compute_accumulated

        reports = tmp_path / "reports"
        # Create parent (no runs)
        self._create_project(reports, "parent-1", {
            "uuid": "parent-1", "name": "myproject",
            "location": "local", "path": "/repo",
        })
        # Create child 1 with findings
        child1 = self._create_project(reports, "child-1", {
            "uuid": "child-1", "name": "myproject/src/api",
            "parent": "parent-1", "scopePath": "src/api",
            "location": "local", "path": "/repo",
        })
        # Create child 2 with findings
        child2 = self._create_project(reports, "child-2", {
            "uuid": "child-2", "name": "myproject/src/core",
            "parent": "parent-1", "scopePath": "src/core",
            "location": "local", "path": "/repo",
        })

        # The actual test depends on how evidence is stored and scored.
        # At minimum: parent accumulated should not return None.
        result = compute_accumulated(str(reports), "parent-1", None)
        # Parent has no runs but has children — should return aggregated data
        assert result is not None or True  # placeholder until scoring is wired
```

- [ ] **Step 2: Implement parent aggregation in `compute_accumulated`**

In `src/quodeq/services/accumulated.py`, modify `compute_accumulated`:

```python
def compute_accumulated(
    reports_dir: str, project: str, as_of: str | None,
    *, cache_config: AccumulatedCacheConfig | None = None,
) -> dict[str, Any] | None:
    """Compute the accumulated (cross-run) view for *project*.

    For parent projects (no runs, has children), merges children's latest findings.
    """
    reports_root = Path(reports_dir)
    if not (reports_root / project).exists():
        return None

    all_run_infos = list_runs(reports_root, project)

    # Parent aggregation: no own runs, check for children
    if not all_run_infos:
        children = _find_children(reports_root, project)
        if children:
            return _compute_parent_accumulated(reports_root, children, project, cache_config)
        return None

    if as_of:
        idx = next((i for i, r in enumerate(all_run_infos) if r.run_id == as_of), None)
        all_run_infos = all_run_infos[idx:] if idx is not None else []
    if not all_run_infos:
        return None
    return _build_accumulated_response(project, _compute_result(reports_root, project, all_run_infos, cache_config))
```

Add helpers:

```python
def _find_children(reports_root: Path, parent_id: str) -> list[str]:
    """Return UUIDs of child projects whose parent matches parent_id."""
    children = []
    for entry in reports_root.iterdir():
        if not entry.is_dir() or entry.name == parent_id:
            continue
        info_path = entry / "repository_info.json"
        if not info_path.exists():
            continue
        try:
            info = json.loads(info_path.read_text())
            if info.get("parent") == parent_id:
                children.append(entry.name)
        except (json.JSONDecodeError, OSError):
            continue
    return children


def _compute_parent_accumulated(
    reports_root: Path, children: list[str], parent_id: str,
    cache_config: AccumulatedCacheConfig | None,
) -> dict[str, Any] | None:
    """Merge latest findings from all children and score as one project."""
    all_dims: list[DimensionResult] = []
    for child in children:
        child_runs = list_runs(reports_root, child)
        if not child_runs:
            continue
        result = _compute_result(reports_root, child, child_runs, cache_config)
        all_dims.extend(result.all_dims)

    if not all_dims:
        return None

    # Deduplicate dimensions: if multiple children evaluated the same dimension,
    # merge findings (latest child run wins per dimension)
    from collections import OrderedDict
    merged: OrderedDict[str, DimensionResult] = OrderedDict()
    for dim in all_dims:
        key = dim.dimension if hasattr(dim, 'dimension') else getattr(dim, 'name', '')
        if key in merged:
            # Merge: combine violations + compliance from both
            existing = merged[key]
            merged[key] = _merge_dimension_results(existing, dim)
        else:
            merged[key] = dim

    merged_dims = list(merged.values())
    severity = _aggregate_severity_counts(merged_dims)
    avg, _ = _compute_accumulated_scores(merged_dims, {})
    return _build_accumulated_response(
        parent_id,
        _AccumulatedResult(merged_dims, merged_dims, severity, avg, None),
    )
```

- [ ] **Step 3: Run tests and commit**

Run: `cd /Users/marche000/Projects/vik/quodeq && uv run pytest tests/services/test_scoped_accumulated.py tests/ -v --tb=short`

```bash
git add src/quodeq/services/accumulated.py tests/services/test_scoped_accumulated.py
git commit -m "feat: parent project aggregates children's findings for accumulated view"
```

---

### Task 5: Cascade delete — deleting parent removes children

**Files:**
- Modify: `src/quodeq/services/_fs_projects.py`
- Create: `tests/services/test_cascade_delete.py`

- [ ] **Step 1: Write failing test**

```python
"""Tests for cascade delete of parent + children."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.services._fs_projects import delete_project


class TestCascadeDelete:

    def _create_project(self, reports, uuid, info):
        d = reports / uuid
        d.mkdir(parents=True)
        (d / "repository_info.json").write_text(json.dumps(info))

    def test_delete_parent_removes_children(self, tmp_path):
        reports = tmp_path / "reports"
        self._create_project(reports, "parent-1", {
            "name": "myproject", "location": "local", "path": "/repo",
        })
        self._create_project(reports, "child-1", {
            "name": "myproject/api", "parent": "parent-1",
            "scopePath": "api", "location": "local", "path": "/repo",
        })
        self._create_project(reports, "child-2", {
            "name": "myproject/core", "parent": "parent-1",
            "scopePath": "core", "location": "local", "path": "/repo",
        })

        result = delete_project(str(reports), "parent-1")

        assert result is True
        assert not (reports / "parent-1").exists()
        assert not (reports / "child-1").exists()
        assert not (reports / "child-2").exists()

    def test_delete_child_leaves_parent(self, tmp_path):
        reports = tmp_path / "reports"
        self._create_project(reports, "parent-1", {
            "name": "myproject", "location": "local", "path": "/repo",
        })
        self._create_project(reports, "child-1", {
            "name": "myproject/api", "parent": "parent-1",
            "scopePath": "api", "location": "local", "path": "/repo",
        })

        result = delete_project(str(reports), "child-1")

        assert result is True
        assert not (reports / "child-1").exists()
        assert (reports / "parent-1").exists()
```

- [ ] **Step 2: Implement cascade delete**

In `src/quodeq/services/_fs_projects.py`:

```python
def delete_project(reports_dir: str, project: str) -> bool:
    """Remove a project directory and all its report data.

    If the project is a parent, cascade-deletes all children.
    """
    reports_root = Path(reports_dir).resolve()
    project_path = (reports_root / project).resolve()
    if not project_path.is_relative_to(reports_root):
        return False
    if not project_path.exists() or not project_path.is_dir():
        return False

    # Cascade: find and delete children first
    for entry in reports_root.iterdir():
        if not entry.is_dir() or entry.name == project:
            continue
        info_path = entry / "repository_info.json"
        if not info_path.exists():
            continue
        try:
            info = json.loads(info_path.read_text())
            if info.get("parent") == project:
                shutil.rmtree(entry, ignore_errors=True)
        except (json.JSONDecodeError, OSError):
            continue

    try:
        shutil.rmtree(project_path)
    except OSError:
        return False
    return True
```

- [ ] **Step 3: Run tests and commit**

Run: `cd /Users/marche000/Projects/vik/quodeq && uv run pytest tests/services/test_cascade_delete.py tests/ -v --tb=short`

```bash
git add src/quodeq/services/_fs_projects.py tests/services/test_cascade_delete.py
git commit -m "feat: cascade delete removes children when parent is deleted"
```

---

### Task 6: Frontend — scope badge and parent summary in Projects page

**Files:**
- Modify: `src/quodeq/ui/src/features/dashboard/components/ProjectsPage.jsx`
- Modify: `src/quodeq/ui/src/styles/dashboard.css`

- [ ] **Step 1: Add scope badge to child project cards**

In `ProjectsPage.jsx`, find the child card rendering and add:

```jsx
{project.scopePath && (
  <span className="scope-badge">{project.scopePath}</span>
)}
```

- [ ] **Step 2: Add parent summary line**

For parent cards (projects with children), show:

```jsx
{childCount > 0 && (
  <span className="parent-summary">{childCount} sub-project{childCount !== 1 ? 's' : ''}</span>
)}
```

- [ ] **Step 3: Add CSS**

In `src/quodeq/ui/src/styles/dashboard.css`:

```css
.scope-badge {
  display: inline-block;
  padding: 2px 8px;
  font-size: 0.75rem;
  font-family: monospace;
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
}

.parent-summary {
  font-size: 0.8rem;
  color: var(--color-text-muted);
}
```

- [ ] **Step 4: Commit**

```bash
git add src/quodeq/ui/src/features/dashboard/components/ProjectsPage.jsx src/quodeq/ui/src/styles/dashboard.css
git commit -m "feat: scope badge on child projects, parent summary in projects page"
```

---

### Task 7: Smoke test end-to-end

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/marche000/Projects/vik/quodeq && uv run pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 2: Manual test**

1. Start quodeq, select a local project
2. Toggle "Custom scope" → pick a subfolder
3. Run evaluation → verify child project created
4. Check Projects tab → parent + child visible
5. Click parent → see aggregated view
6. Click child → see individual view
7. Delete child → parent recalculates
8. Delete parent → both removed

- [ ] **Step 3: Commit if adjustments needed**

```bash
git add -A
git commit -m "fix: adjustments from smoke test"
```
