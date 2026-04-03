# Architecture

## Layer Overview

| Layer | Purpose | Dependencies |
|-------|---------|--------------|
| `core/` | Domain logic: evidence models, scoring algorithms, standards definitions, type definitions | None (stdlib only) |
| `engine/` | Infrastructure and execution: pipeline orchestration, markers, runner utilities | core/, analysis/ |
| `data/` | Data access: filesystem repositories, web API clients, report parsers | core/ |
| `services/` | Business logic: dashboard, accumulated views, dismissals, standards CRUD | core/, data/ (via `services/ports.py`) |
| `api/` | HTTP layer: Flask routes, security, rate limiting | core/, services/ |
| `analysis/` | Evaluation pipeline: AI orchestration, subagents, prompts, MCP | core/, engine/, data/, services/ |
| `dashboard/` | Server/process management: build UI, start API, health checks | services/, api/ |
| `shared/` | Cross-cutting utilities: config, logging, env helpers | None (stdlib only) |
| `config/` | Configuration: paths, discipline detection, standards fetching | shared/ |

## Import Rules

```
core/          -> stdlib, core/ only
engine/        -> stdlib, core/, analysis/
data/          -> stdlib, core/
services/      -> stdlib, core/, data/ (via services/ports.py)
api/           -> stdlib, core/, services/
analysis/      -> stdlib, core/, engine/, data/, services/
dashboard/     -> stdlib, services/, api/
shared/        -> stdlib only
config/        -> stdlib, shared/
```

## File Size Guidelines (soft limits)

| Metric | Limit | Rationale |
|--------|-------|-----------|
| File lines | 100 | Fits in one context window |
| Function lines | 50 | Single-screen readable |
| Imports per file | 15 | Signals too many responsibilities |
| Functions per file | 12 | Beyond this, split the file |

## Conventions

- Private modules use `_` prefix (e.g., `_fs_projects.py`).
- Public APIs live in the parent `__init__.py` with re-exports for backward compatibility.
- Frozen dataclasses for data transfer objects.
- `services/ports.py` is the single boundary between services and data layers.
