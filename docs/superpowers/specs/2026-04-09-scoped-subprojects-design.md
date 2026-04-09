# Scoped Sub-Projects Design

## Goal

Allow users to evaluate a subfolder or single file within a project, creating a child project (sub-project) that maintains its own evaluation history while contributing findings to the parent project's aggregated scores.

## Architecture

Sub-projects are full projects with a `parent` link and a `scopePath`. The parent project is a container whose scores are computed at read-time by merging findings from all children. No new data models — extends the existing project/run/scoring infrastructure.

## Key Concepts

- **Parent project**: created from the full repo path. Has no runs of its own. Its accumulated view merges children's findings.
- **Child project (sub-project)**: created from parent UUID + scopePath. Has its own runs, history, scores, trends — a full project in every sense.
- **Scope path**: relative path within the repo (e.g. `src/api`, `lib/core/parser.py`). Can be a folder or file.

---

## 1. Project Creation Flow

When a user evaluates with a custom scope:

1. **Parent project** is resolved/created first using the full repo path (same as today's `resolve_project_uuid`).
2. **Child project** is created with:
   - `parent`: parent's UUID
   - `scopePath`: relative path (e.g. `src/api`)
   - `name`: `{parent_name}/{scopePath}`
   - `path`: same as parent (full repo path)
   - Own UUID, own directory under `/reports/{child_uuid}/`
3. The evaluation runs against scoped files but stores results under the child project.
4. Re-evaluating the same scope reuses the existing child project (matched by `parent_uuid + scopePath`).

### repository_info.json (child)

```json
{
  "uuid": "child-uuid",
  "name": "myproject/src/api",
  "discipline": null,
  "location": "local",
  "path": "/Users/me/myproject",
  "parent": "parent-uuid",
  "scopePath": "src/api"
}
```

### Project Resolution

`resolve_project_uuid` gains a `scope_path` parameter:
- If `scope_path` is set, first resolve/create the parent (full repo), then resolve/create the child using the key `(parent_uuid, scope_path)`.
- Lookup in `project_index.json` uses a composite key: `name\0path\0scopePath` for scoped projects.

---

## 2. Parent Accumulated Scores

The parent project has no runs. Its accumulated view is computed at read-time:

1. List all child projects (by `parent` field).
2. For each child, load the latest completed run's evidence JSONL.
3. Merge all findings into a single pool. Deduplicate by `(file, line, req)`.
4. Run the standard scoring pipeline on the merged findings.
5. Cache the result. Invalidate when any child gets a new evaluation.

### Cache Invalidation

Store a `children_hash` in the parent directory — a hash of `(child_uuid, latest_run_id)` pairs. When the accumulated endpoint is called, recompute the hash. If it differs from cached, re-merge and re-score. Otherwise return cached result.

### API

`GET /api/projects/{parent}/accumulated` — detects children exist, triggers merge-and-score path instead of the normal single-project accumulated path.

`GET /api/projects/{parent}/dashboard` — same: uses merged data for the overview.

---

## 3. Projects UI

The Projects page already renders parent/child trees via `computeProjectTree()` and `ProjectCardGroup`.

### Parent Card

- Shows aggregated grade/score from merged children findings.
- Summary line: "N sub-projects evaluated".
- No "Re-evaluate" button — evaluations happen at the child level.
- Click navigates to aggregated overview dashboard.

### Child Card

- Shows its own individual grades/scores (as today).
- Displays `scopePath` badge (e.g. `src/api`).
- Has "Re-evaluate" and "Re-scan changes" buttons.
- Click navigates to that child's individual dashboard.

No new UI components needed.

---

## 4. Evaluate Screen Integration

### New Evaluation with Scope

1. User enters local path → scan runs on full project.
2. User toggles "Custom scope" → picks subfolder/file.
3. Payload: `{ repo: "/path/to/project", scopePath: "src/api", dimensions: [...] }`.
4. Backend:
   - Resolves/creates parent project from `repo`.
   - Resolves/creates child project from `parent_uuid + scopePath`.
   - Passes `--scope src/api` to CLI.
   - Run stored under child project directory.

### Re-evaluate with Scope

- Re-evaluate card for a child project pre-fills its `scopePath`.
- Scope browser roots at the parent's full repo path.
- Re-evaluate card for a parent shows existing sub-projects and an option to add a new scope.

### Payload Changes

`startEvaluation` payload gains `scopePath: string | null`. The `_evaluation_helpers.py` parser passes it through to the CLI via `--scope`.

---

## 5. CLI Changes

The `--scope` argument (already exists in `cli_parser.py`) behavior changes:

- Language detection runs on the **full repo** (not scoped path).
- Manifest is built from the full repo, then **filtered** to files under `scopePath`.
- The evaluation subprocess receives the filtered manifest.
- Results are stored under the child project's run directory.

This is already partially implemented (the scope filter in `cli.py` from the previous PR).

---

## 6. Deletion & Data Integrity

- **Delete child**: removes child project directory. Parent recalculates without it.
- **Delete parent**: cascade-deletes all children. Confirmation dialog warns.
- **Scope uniqueness**: `(parent_uuid, scopePath)` is unique. Enforced at resolution time.

---

## 7. Migration

No data migration needed:
- Existing projects with no children work exactly as today.
- The parent aggregation path only activates when `children` are detected.
- `repository_info.json` gains optional `parent` and `scopePath` fields.
- `project_index.json` gains scoped entries alongside existing ones.

---

## Files to Change

### Backend
- `src/quodeq/data/fs/project_resolver.py` — scope-aware resolution
- `src/quodeq/data/fs/_models.py` — add `scopePath` to ProjectIdentity
- `src/quodeq/services/evaluation_mixin.py` — pass scope through to project creation
- `src/quodeq/services/_fs_projects.py` — list children, cascade delete
- `src/quodeq/services/accumulated.py` — merge-and-score path for parents
- `src/quodeq/api/_evaluation_helpers.py` — parse `scopePath` from payload
- `src/quodeq/api/routes_project_list.py` — cascade delete endpoint
- `src/quodeq/cli.py` — scope filter (partially done)

### Frontend
- `src/quodeq/ui/src/features/evaluation/hooks/useEvaluation.js` — send `scopePath` in payload
- `src/quodeq/ui/src/features/evaluation/components/ReEvaluateCard.jsx` — show scopePath, parent re-eval options
- `src/quodeq/ui/src/features/dashboard/components/ProjectsPage.jsx` — parent summary line, child scope badge
- `src/quodeq/ui/src/features/dashboard/hooks/useDashboard.js` — handle parent merged view
