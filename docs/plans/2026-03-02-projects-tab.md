# Projects Tab Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the sidebar project dropdown with a dedicated Projects tab that shows all projects in a collapsible tree with grade/date info and supports parent/child relationships.

**Architecture:** Add `parent` to the backend `list_projects` response by reading `repository_info.json`. Add a new `projects` page to the frontend nav stack, rendered by a new `ProjectsPage.jsx`. Remove the inline sidebar dropdown. Update the content header to show `parent › child` when a child project is selected.

**Tech Stack:** Python (backend), React + CSS custom properties (frontend), no new dependencies.

---

### Task 1: Backend — expose `parent` in list_projects

**Files:**
- Modify: `src/quodeq/action_provider_fs.py:123-141`

**Step 1: Edit `list_projects` to read `repository_info.json` per project**

In `FilesystemActionProvider.list_projects`, after computing `runs`, peek at the project's `repository_info.json` and extract `parent` if present. Replace the current `projects.append(...)` block with:

```python
def list_projects(self, reports_dir: str):
    reports_root = Path(reports_dir)
    projects = []
    for entry in _safe_read_dir(reports_root):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        runs = _list_runs(reports_root, entry.name)
        if not runs:
            continue
        parent = None
        info_path = reports_root / entry.name / "repository_info.json"
        if info_path.exists():
            try:
                info = json.loads(info_path.read_text())
                parent = info.get("parent") or None
            except (json.JSONDecodeError, OSError):
                pass
        projects.append(
            {
                "name": entry.name,
                "runsCount": len(runs),
                "latestRunId": runs[0].run_id if runs else None,
                "latestDate": runs[0].date_iso if runs else None,
                "parent": parent,
            }
        )
    projects.sort(key=lambda item: item["name"])
    return {"projects": projects}
```

**Step 2: Verify manually**

Start the backend and call:
```
curl http://localhost:5000/api/projects
```
Expected: each project object includes a `"parent"` key (null if not set). Add a `"parent": "some-project"` entry to any `repository_info.json` and re-call to confirm it appears.

**Step 3: Commit**

```bash
git add src/quodeq/action_provider_fs.py
git commit -m "feat: include parent field in list_projects response"
```

---

### Task 2: App.jsx — add Projects nav item, remove dropdown

**Files:**
- Modify: `ui/web/src/App.jsx`

This task has several small edits. Do them all before committing.

**Step 1: Add the Projects icon constant** (after `ICON_EVALUATE`, before `ICON_SETTINGS`)

```jsx
const ICON_PROJECTS = (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 7h18M3 12h18M3 17h18" />
    <rect x="3" y="3" width="4" height="4" rx="0.5" />
    <rect x="3" y="10" width="4" height="4" rx="0.5" />
    <rect x="3" y="17" width="4" height="4" rx="0.5" />
  </svg>
);
```

**Step 2: Expand `activeTab` to include `'projects'`** (line ~292)

Change:
```js
const activeTab = ['overview', 'evaluate', 'settings'].includes(activePage.page)
  ? activePage.page
  : 'overview';
```
To:
```js
const activeTab = ['overview', 'projects', 'evaluate', 'settings'].includes(activePage.page)
  ? activePage.page
  : 'overview';
```

**Step 3: Update `showProjectHeader`** (line ~297)

Change:
```js
const showProjectHeader = activeTab === 'overview' && projects.length > 0 && !!selectedProject;
```
To:
```js
const showProjectHeader = ['overview'].includes(activeTab) && projects.length > 0 && !!selectedProject;
```

(This excludes the `projects` tab from showing the project header.)

**Step 4: Add the Projects nav button in the sidebar** (after the Evaluate button, before the closing `</nav>`)

```jsx
<button
  type="button"
  className={`sidebar-nav-item${activeTab === 'projects' ? ' active' : ''}`}
  onClick={() => navTab('projects')}
  title="Projects"
>
  {ICON_PROJECTS}
  <span className="sidebar-nav-label">Projects</span>
</button>
```

**Step 5: Remove the entire `sidebar-project-section` block** (lines ~617-633)

Delete:
```jsx
{/* Project selector */}
{projects.length > 0 && (
  <div className="sidebar-project-section">
    <p className="sidebar-project-label">Project</p>
    <select
      className="project-select-styled"
      value={selectedProject}
      disabled={projects.length === 0}
      onChange={(e) => handleProjectChange(e.target.value)}
    >
      {projects.map((p) => {
        const name = p.name || p;
        return <option key={name} value={name}>{name}</option>;
      })}
    </select>
  </div>
)}
```

**Step 6: Add `case 'projects'` stub in `renderContent`** (before the `default:` case)

```jsx
case 'projects':
  return (
    <ProjectsPage
      projects={projects}
      selectedProject={selectedProject}
      onSelect={(name) => { handleProjectChange(name); navTab('overview'); }}
    />
  );
```

**Step 7: Add the import for `ProjectsPage`** at the top of the file (after the existing imports)

```jsx
import ProjectsPage from './features/dashboard/components/ProjectsPage.jsx';
```

**Step 8: Verify the app builds**

```bash
cd ui/web && npm run build
```
Expected: no errors. The app should load, show three nav items, and clicking Projects should hit the stub (which will show nothing until Task 3).

**Step 9: Commit**

```bash
git add ui/web/src/App.jsx
git commit -m "feat: add Projects nav tab, remove sidebar dropdown"
```

---

### Task 3: ProjectsPage.jsx — tree component

**Files:**
- Create: `ui/web/src/features/dashboard/components/ProjectsPage.jsx`

**Step 1: Create the component**

```jsx
import { useState } from 'react';

function gradeLabel(grade) {
  if (!grade) return null;
  const k = grade.trim().toLowerCase();
  // Map verbose grades to single letter
  const MAP = { exemplary: 'A', good: 'B', proficient: 'B', adequate: 'C', developing: 'C', poor: 'D', insufficient: 'D', critical: 'F' };
  const letter = MAP[k] ?? grade.trim().toUpperCase().charAt(0);
  return letter;
}

function formatDate(iso) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  } catch {
    return null;
  }
}

export default function ProjectsPage({ projects = [], selectedProject, onSelect }) {
  // Build tree
  const projectMap = Object.fromEntries(projects.map((p) => [p.name || p, p]));
  const children = {};
  const roots = [];

  for (const p of projects) {
    const name = p.name || p;
    const parent = p.parent;
    if (parent && projectMap[parent]) {
      if (!children[parent]) children[parent] = [];
      children[parent].push(p);
    } else {
      roots.push(p);
    }
  }

  // Default: expand the parent of the selected project (if any)
  const selectedData = projectMap[selectedProject];
  const initialExpanded = selectedData?.parent ? { [selectedData.parent]: true } : {};
  // Also expand any root that has children
  roots.forEach((p) => {
    const name = p.name || p;
    if (children[name]?.length) initialExpanded[name] = true;
  });

  const [expanded, setExpanded] = useState(initialExpanded);

  function toggle(name) {
    setExpanded((prev) => ({ ...prev, [name]: !prev[name] }));
  }

  function renderRow(p, depth = 0) {
    const name = p.name || p;
    const hasChildren = !!(children[name]?.length);
    const isSelected = name === selectedProject;
    const grade = gradeLabel(p.overallGrade ?? p.latestGrade);
    const score = p.latestScore != null ? parseFloat(p.latestScore).toFixed(1)
                : p.numericAverage != null ? parseFloat(p.numericAverage).toFixed(1)
                : null;
    const date = formatDate(p.latestDate);
    const isExpanded = expanded[name];

    return (
      <div key={name}>
        <div
          className={`projects-row${isSelected ? ' projects-row--selected' : ''}${depth > 0 ? ' projects-row--child' : ''}`}
          style={{ '--depth': depth }}
        >
          <span
            className={`projects-chevron${hasChildren ? '' : ' projects-chevron--hidden'}`}
            onClick={hasChildren ? () => toggle(name) : undefined}
          >
            {hasChildren ? (isExpanded ? '▾' : '▸') : ''}
          </span>
          <span className="projects-row-name" onClick={() => onSelect(name)}>
            {name}
          </span>
          <span className="projects-row-meta">
            {(grade || score) && (
              <span className={`projects-grade projects-grade--${(grade ?? 'x').toLowerCase()}`}>
                {grade}{score ? ` ${score}` : ''}
              </span>
            )}
            {date && <span className="projects-date">{date}</span>}
          </span>
        </div>
        {hasChildren && isExpanded && children[name].map((child) => renderRow(child, depth + 1))}
      </div>
    );
  }

  return (
    <section className="projects-page">
      <div className="projects-header">
        <h1 className="projects-title">Projects</h1>
      </div>
      {projects.length === 0 ? (
        <div className="projects-empty">
          <p>No projects yet. Run an evaluation to get started.</p>
        </div>
      ) : (
        <div className="projects-list panel">
          {roots.map((p) => renderRow(p, 0))}
        </div>
      )}
    </section>
  );
}
```

**Step 2: Verify the build**

```bash
cd ui/web && npm run build
```
Expected: no errors.

**Step 3: Commit**

```bash
git add ui/web/src/features/dashboard/components/ProjectsPage.jsx
git commit -m "feat: add ProjectsPage tree component"
```

---

### Task 4: CSS — projects page styles

**Files:**
- Modify: `ui/web/src/styles/dashboard.css` (append at end)

**Step 1: Append styles**

```css
/* ── Projects page ─────────────────────────────────────── */

.projects-page {
  padding: var(--space-6);
  max-width: 720px;
}

.projects-header {
  margin-bottom: var(--space-5);
}

.projects-title {
  font-size: var(--text-xl);
  font-weight: var(--weight-semibold);
  color: var(--color-text);
  margin: 0;
}

.projects-list {
  padding: var(--space-2) 0;
}

.projects-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  padding-left: calc(var(--space-4) + var(--depth, 0) * 20px);
  border-radius: var(--radius-sm);
  cursor: default;
  transition: background 120ms ease;
}

.projects-row:hover {
  background: color-mix(in srgb, var(--color-accent) 5%, transparent);
}

.projects-row--selected {
  background: color-mix(in srgb, var(--color-accent) 10%, transparent);
}

.projects-row--child {
  font-size: var(--text-sm);
}

.projects-chevron {
  width: 14px;
  font-size: 11px;
  color: var(--color-text-muted);
  cursor: pointer;
  flex-shrink: 0;
  user-select: none;
}

.projects-chevron--hidden {
  visibility: hidden;
  cursor: default;
  pointer-events: none;
}

.projects-row-name {
  flex: 1;
  color: var(--color-text);
  cursor: pointer;
  font-weight: var(--weight-medium);
}

.projects-row-name:hover {
  color: var(--color-accent);
}

.projects-row--selected .projects-row-name {
  color: var(--color-accent);
}

.projects-row-meta {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  flex-shrink: 0;
}

.projects-grade {
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, currentColor 12%, transparent);
  letter-spacing: 0.03em;
}

.projects-grade--a { color: var(--color-grade-top-text); }
.projects-grade--b { color: var(--color-grade-high-text); }
.projects-grade--c { color: var(--color-grade-mid-text); }
.projects-grade--d { color: var(--color-grade-low-text); }
.projects-grade--f { color: var(--color-grade-bottom-text); }
.projects-grade--x { color: var(--color-text-muted); }

.projects-date {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  min-width: 48px;
  text-align: right;
}

.projects-empty {
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  padding: var(--space-6);
}
```

**Step 2: Verify the build**

```bash
cd ui/web && npm run build
```
Expected: no errors.

**Step 3: Commit**

```bash
git add ui/web/src/styles/dashboard.css
git commit -m "feat: add projects page styles"
```

---

### Task 5: App.jsx — parent › child in content header

**Files:**
- Modify: `ui/web/src/App.jsx`

**Step 1: Add a `selectedProjectParent` derived value** (after the `headerMeta` useMemo, around line ~206)

```js
const selectedProjectParent = useMemo(() => {
  if (!selectedProject || !projects.length) return null;
  const data = projects.find((p) => (p.name || p) === selectedProject);
  return data?.parent || null;
}, [selectedProject, projects]);
```

**Step 2: Update the `<h1>` in the content header** (around line ~642)

Change:
```jsx
<h1 className="content-project-name">{selectedProject}</h1>
```
To:
```jsx
<h1 className="content-project-name">
  {selectedProjectParent && (
    <>
      <span className="content-project-parent">{selectedProjectParent}</span>
      <span className="content-project-sep">›</span>
    </>
  )}
  {selectedProject}
</h1>
```

**Step 3: Add CSS for the parent label** in `ui/web/src/styles/base.css` (append to the content-header section, or add after `.content-project-name` styles)

Find where `.content-project-name` is defined and append:
```css
.content-project-parent {
  color: var(--color-text-muted);
  font-weight: var(--weight-normal);
}

.content-project-sep {
  color: var(--color-text-muted);
  margin: 0 var(--space-2);
  font-weight: var(--weight-normal);
}
```

**Step 4: Verify the build**

```bash
cd ui/web && npm run build
```
Expected: no errors.

**Step 5: Commit**

```bash
git add ui/web/src/App.jsx ui/web/src/styles/base.css
git commit -m "feat: show parent › child in content header"
```

---

### Task 6: Wire up grade/score data from list_projects

**Context:** `ProjectsPage` references `p.overallGrade`, `p.latestGrade`, `p.latestScore`, `p.numericAverage` — but currently `list_projects` only returns `name`, `runsCount`, `latestRunId`, `latestDate`, `parent`. The grade/score need to come from somewhere.

The `latestDate` already exists. For grade/score: the simplest approach is to read the latest run summary from the reports folder in `list_projects`.

**Files:**
- Modify: `src/quodeq/action_provider_fs.py:123-141` (the list_projects method from Task 1)

**Step 1: Extend `list_projects` to include latest grade/score**

The summary data is stored per-run. Look at how `get_dashboard` works: it calls `_read_run_data` and `_summarize_dimensions`. We need the overall grade/score from the latest run.

Read the `_summarize_dimensions` helper to understand what it returns (it's in the same file). Then add a helper call to get the summary for the latest run:

```python
# After computing runs, get latest run summary
latest_grade = None
latest_score = None
if runs:
    try:
        dims = _read_run_data(reports_root, entry.name, runs[0].run_id)
        summary = _summarize_dimensions(dims)
        latest_grade = summary.get("overallGrade")
        latest_score = summary.get("numericAverage")
    except Exception:
        pass

projects.append(
    {
        "name": entry.name,
        "runsCount": len(runs),
        "latestRunId": runs[0].run_id if runs else None,
        "latestDate": runs[0].date_iso if runs else None,
        "parent": parent,
        "latestGrade": latest_grade,
        "latestScore": latest_score,
    }
)
```

**Step 2: Check what `_summarize_dimensions` returns**

Search the file for `def _summarize_dimensions` and read its return value to confirm `overallGrade` and `numericAverage` are the right keys.

**Step 3: Verify manually**

```
curl http://localhost:5000/api/projects
```
Expected: each project includes `latestGrade` (e.g. `"good"`) and `latestScore` (e.g. `7.4`).

**Step 4: Commit**

```bash
git add src/quodeq/action_provider_fs.py
git commit -m "feat: include latestGrade and latestScore in list_projects"
```

---

### Task 7: Final smoke test

**Step 1:** Start the full stack (backend + `npm run dev`)

**Step 2:** Open the app. Confirm:
- Three nav items visible: Overview, Projects, Evaluate
- No project dropdown in sidebar
- Clicking Projects shows the projects list with names, grades, dates
- Add `"parent": "some-parent"` to a project's `repository_info.json`, restart backend, reload — confirm the child appears indented under the parent
- Selecting a child project navigates to Overview with `parent › child` in the header
- Selecting a root (parent) project shows only its name in the header

**Step 3: Commit (if any loose ends)**

```bash
git push
```
