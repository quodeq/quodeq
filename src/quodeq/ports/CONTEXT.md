# Ports Context

This directory (`src/quodeq/ports/`) contains only this document. No Python modules live here. The real Protocols are spread across the codebase; use the "Where ports actually live" section below as the index. This doc records the vocabulary the codebase uses for those boundaries.

## Language

**Port (Interface)**:
A `typing.Protocol` (sometimes `@runtime_checkable`) that specifies what a layer needs from its collaborators without naming a concrete implementation. Canonical example: [`data/ports/findings.py:10`](../data/ports/findings.py) defines `FindingsRepository`.

**Adapter (Implementation)**:
The concrete class that satisfies a Port. Canonical example: [`data/sqlite/findings_repository.py:33`](../data/sqlite/findings_repository.py) defines `SqliteFindingsRepository`. Some Ports have multiple Adapters and act as real swap points (for example `EvaluationsRepository` has Filesystem, Hybrid, and Web variants in [`data/fs/`](../data/fs/evaluations_repository.py), [`data/hybrid/`](../data/hybrid/evaluations_repository.py), and [`data/web/`](../data/web/evaluations_repository.py)). Others have a single Adapter today and exist mainly as a typed seam.

**Data Port**:
A Port specialised for the lifecycle of a domain entity (Finding, Evaluation, Dimension), defined under [`data/ports/`](../data/ports/). These are the structured access points to the **Event Log** (JSONL) and **State Store** (SQLite); see the top-level [CONTEXT.md](../../../CONTEXT.md) for those terms.

**Repository Pattern**:
The shape used for Data Ports: a collection-like API (`insert_finding`, `list_by_dimension`, `count_by_dimension`, and so on) that hides whether the data lives in a SQLite projection, a JSONL file, or an HTTP endpoint.

## Vocabulary not currently used

An earlier version of this doc described **Outbound Port** and **Inbound Port** as a formal pair. The codebase does not label any Protocol with those terms today. The closest "inbound" candidate is [`services/base.py:136`](../services/base.py) `ActionProvider`, which the Flask API typehints in [`api/routes_registry.py`](../api/routes_registry.py). The CLI ([`_cli_evaluation.py`](../_cli_evaluation.py), [`_cli_resolution.py`](../_cli_resolution.py)) does not go through `ActionProvider`, so the "all external actors enter through an Inbound Port" framing does not hold. The vocabulary is omitted until the code reflects it.

## Where ports actually live

- [`data/ports/`](../data/ports/): persistence Protocols (`FindingsRepository`, `EvaluationsRepository`, `DimensionsRepository`) plus the `DataError` exception hierarchy.
- [`services/ports.py`](../services/ports.py): services-layer boundary module. Re-exports `FindingsRepository` and defines `RunStorage` (satisfied today by module-level functions in [`data/fs/report_parser/runs.py`](../data/fs/report_parser/runs.py), not a class).
- [`services/base.py`](../services/base.py): service-facing Protocols `ProjectActions`, `ReportActions`, `EvaluationActions`, `ToolingActions`, and the composite `ActionProvider`. Implemented by [`services/filesystem.py:39`](../services/filesystem.py) `FilesystemActionProvider`.
- [`services/_job_model.py`](../services/_job_model.py): `JobStore` Protocol with `InMemoryJobStore` and `FileJobStore` adapters.
- [`api/_rate_limit_store.py`](../api/_rate_limit_store.py): `RateLimitStore` Protocol with `InMemoryRateLimitStore` and [`api/_rate_limit_file_store.py`](../api/_rate_limit_file_store.py) `FileRateLimitStore` adapters.
- [`analysis/cache/backend.py`](../analysis/cache/backend.py): `CacheBackend` Protocol with `LocalFileBackend` and `TieredCache` adapters.
- [`analysis/cache/runner.py`](../analysis/cache/runner.py), [`analysis/mcp/`](../analysis/mcp/), [`analysis/subagents/`](../analysis/subagents/): smaller Protocols local to the analysis pipeline (`Dispatcher`, `FileReader`, `DeduplicationStore`, `WorkQueue`).
- [`core/utils/locking.py`](../core/utils/locking.py): `FileLock` Protocol with `_UnixFileLock` and `_WindowsFileLock` platform adapters.

For layer boundaries and import rules see [ARCHITECTURE.md](../../../ARCHITECTURE.md), which documents [`services/ports.py`](../services/ports.py) as the single boundary between the services and data layers.

## Relationships

- **Adapters** implement **Ports** to connect services to filesystem, SQLite, or HTTP backends.
- **Data Ports** are the structured entry points to the **Event Log** and **State Store** (see [data/CONTEXT.md](../data/CONTEXT.md)).
- Swapping a backend (for example SQLite to PostgreSQL) requires a new **Adapter** and registration at the construction site, leaving the **Port** untouched.
