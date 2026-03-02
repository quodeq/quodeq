# Projects Tab Design

**Date:** 2026-03-02
**Status:** Approved

## Problem

The project selector is an inline `<select>` dropdown buried in the sidebar. It gives no overview of available projects, no indication of quality, no run dates, and no way to express relationships between projects (e.g. a platform composed of multiple services).

## Goal

Replace the sidebar dropdown with a dedicated **Projects** tab that shows all projects in a tree, supports parent/child relationships, and lets users switch projects from a richer UI.

## Data Model

### Backend change — `list_projects`

`action_provider_fs.py` `list_projects` will peek at each project's `repository_info.json` and include a `parent` field if present. No migration needed — opt-in, existing projects return `parent: null`.

Each project object becomes:
```json
{
  "name": "service-a",
  "runsCount": 12,
  "latestRunId": "run-2026-03-01",
  "latestDate": "2026-03-01T10:00:00Z",
  "parent": "my-platform"
}
```

### Declaring a parent

Add a `parent` key to `repository_info.json` inside the child project's data folder:
```json
{
  "discipline": "backend",
  "parent": "my-platform"
}
```

## Sidebar & Navigation

- New **Projects** nav button between Overview and Evaluate (folder/stack icon)
- Calls `navTab('projects')` — fits existing pattern
- `activeTab` expanded to include `'projects'`
- Current `sidebar-project-section` dropdown **removed**
- `showProjectHeader` updated to exclude the `projects` page

```
[CC]
────
[⊞] Overview
[⬡] Projects
[◎] Evaluate
────
[⚙] Settings
```

## Projects Page Component

New `ProjectsPage.jsx`. Builds a tree client-side from the flat `projects` array.

**Tree structure:**
- Roots: projects with no `parent`
- Children: grouped under their parent by the `parent` field
- Orphaned children (parent not found in list) fall back to root level

**Each row shows:**
- Project name
- Latest score badge (grade-colored, e.g. `B  7.4`)
- Latest run date (muted)

**Interaction:**
- Root projects with children: `▾/▸` chevron toggles expand/collapse
- Clicking the project name selects it and navigates to `overview`
- Children are indented with a subtle connector line
- Selected project row is highlighted
- Empty state if no projects: prompt to go to Evaluate

```
Projects
─────────────────────────────────────────
▾ my-platform          B  7.4    Feb 28
  ├ service-a          C  5.1    Mar 01  ← selected
  └ service-b          A  8.9    Feb 20
  standalone-repo      D  3.2    Jan 15
─────────────────────────────────────────
```

## Overview Header — Parent › Child

When the selected project has a `parent`, the content header title renders:

```
my-platform › service-a
```

- Parent name in muted style
- `›` separator
- Child name as primary text

No change when there is no parent.

## Files Changed

| File | Change |
|---|---|
| `src/codecompass/action_provider_fs.py` | Add `parent` to `list_projects` response |
| `ui/web/src/App.jsx` | Add Projects nav, remove dropdown, add `case 'projects'`, update header |
| `ui/web/src/features/dashboard/components/ProjectsPage.jsx` | New component |
| `ui/web/src/styles/dashboard.css` | Styles for projects page |
