# Clean Architecture: DTO Migration Plan

**Status:** Proposed
**Date:** 2026-03-15
**Goal:** Replace raw `JsonObject` / `dict` data flows with typed DTOs and domain models so every layer has a clear contract — no guessing what's inside a dict.

---

## Problem

The current data flow is:

```
JSON file → json.loads() → dict → passed across layers → hope the keys exist
```

Even with TypedDicts, the data is still structurally a dict — keys can be misspelled, missing fields are only caught at runtime, and there's no validation boundary. A function receiving `DimensionData` (TypedDict) has no guarantee the data actually matches the declared shape.

## Target Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐     ┌──────────────┐
│  JSON/JSONL  │────▶│  Parser/DTO  │────▶│  Domain Model   │────▶│  API Response │
│  (raw bytes) │     │  (validated) │     │  (business logic)│     │  (serialized) │
└─────────────┘     └──────────────┘     └─────────────────┘     └──────────────┘
     disk/net         adapters layer         engine/provider          action_api
```

**Three mapping boundaries:**

1. **Inbound (JSON → DTO):** Parsers validate and map raw JSON into frozen dataclasses. Invalid data is rejected here, not deep in business logic.
2. **DTO → Domain:** DTOs are mapped to domain models that carry behavior (methods, computed properties).
3. **Domain → Response:** Domain models are serialized to API-response dicts only at the Flask route level.

---

## Current State Audit

### Already proper domain models (no change needed)

| Model | File | Usage |
|-------|------|-------|
| `Evidence` | `engine/evidence.py` | Full scoring pipeline |
| `PrincipleEvidence` | `engine/evidence.py` | Per-principle findings |
| `Judgment` | `engine/evidence.py` | Single LLM finding |
| `RunInfo` | `report_parser/runs.py` | Run metadata |
| `ViolationContext` | `provider/violation_context.py` | Parse context |
| `FindingSpec` | `provider/violation_context.py` | Finding builder input |
| `Job` | `provider/jobs.py` | Evaluation job state |
| `DisciplineRule` | `config/discipline_registry.py` | Plugin detection |
| `ConfigPaths` | `config/paths.py` | Path resolution |
| `EvaluationOptions` | `provider/base.py` | Evaluation params |

### Still raw dicts (migration targets)

| Current shape | Where created | Where consumed | Priority |
|---------------|---------------|----------------|----------|
| `DimensionData` (TypedDict) | `runs.read_run_data` | dashboard, accumulated, stale-dims, grades | **P0** — flows everywhere |
| `ParsedReport` (TypedDict) | `json_parser.parse_report_json` | runs, dashboard | P1 |
| `EvidenceFileMeta` (TypedDict) | `json_parser.parse_evidence_file` | runs | P1 |
| `TotalsDict` (TypedDict) | `grades.build_totals` | json_parser, dashboard | P1 |
| `DimensionSummary` (TypedDict) | `grades.summarize_dimensions` | dashboard, accumulated | P1 |
| `FindingDict` (TypedDict) | `violation_context.build_finding_base` | violations_parsing, json_parser | P2 |
| `ViolationResponse` (TypedDict) | `violations_parsing._build_violation_response` | violations, action_api | P2 |
| `ProjectEntry` (TypedDict) | `filesystem._build_project_entry` | filesystem.list_projects | P2 |
| `JobDict` (TypedDict) | `jobs.Job.to_dict` | evaluation_mixin, action_api | P3 |
| `ScoringResult` (TypedDict) | `scoring.run_scoring` | report, rescore | P3 |
| `PluginInfo` (TypedDict) | `plugin_discovery.discover_plugins` | action_api | P3 |
| Dashboard response dict | `dashboard.build_dashboard` | filesystem, action_api | P3 |
| Accumulated response dict | `accumulated.compute_accumulated` | filesystem, action_api | P3 |

---

## Migration Phases

### Phase 0: Foundation (create the DTO layer)

**New module:** `src/quodeq/adapters/fs/report_parser/dto.py`

```python
"""Frozen dataclasses for parsed report data — the DTO layer."""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SeverityTally:
    critical: int = 0
    major: int = 0
    minor: int = 0
    unknown: int = 0


@dataclass(frozen=True)
class Totals:
    violation_count: int
    compliance_count: int
    severity: SeverityTally


@dataclass(frozen=True)
class Finding:
    principle: str | None = None
    file: str | None = None
    line: int | str | None = None
    title: str | None = None
    reason: str | None = None
    snippet: str | None = None
    severity: str = "minor"
    cwe: int | str | None = None
    req: str | None = None
    req_refs: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class EvidenceMeta:
    dimension: str
    source_file_count: int | None = None
    date: str | None = None
    discipline: str | None = None


@dataclass(frozen=True)
class PrincipleGrade:
    name: str | None
    score: str | None = None
    grade: str | None = None


@dataclass(frozen=True)
class DimensionResult:
    """One dimension's merged evaluation + evidence from a run.

    Replaces the current DimensionData TypedDict.
    """
    dimension: str | None = None
    overall_score: str | None = None
    overall_grade: str | None = None
    principles: tuple[PrincipleGrade, ...] = ()
    violations: tuple[Finding, ...] = ()
    compliance: tuple[Finding, ...] = ()
    totals: Totals | None = None
    source_file_count: int | None = None
    evidence_date: str | None = None
    discipline: str | None = None

    # Added by trend/dashboard enrichment (None until set)
    trend: str | None = None
    previous_run_id: str | None = None
    previous_score: str | None = None
    from_run_id: str | None = None
    from_date_iso: str | None = None
    from_date_label: str | None = None
    stale: bool = False
```

**New module:** `src/quodeq/adapters/fs/report_parser/mappers.py`

```python
"""Map raw JSON dicts to frozen DTOs with validation."""

def parse_finding(raw: dict) -> Finding:
    """Validate and map a raw finding dict to a Finding DTO."""
    ...

def parse_dimension_result(raw: dict) -> DimensionResult:
    """Map a raw merged eval+evidence dict to DimensionResult."""
    ...

def dimension_result_to_api(result: DimensionResult) -> dict:
    """Serialize a DimensionResult back to the API response format."""
    ...
```

### Phase 1: DimensionData → DimensionResult (highest impact)

**Why first:** `DimensionData` flows through 6+ modules. Converting it gives the biggest bang.

**Steps:**

1. Create `DimensionResult` dataclass in `dto.py`
2. Create `parse_dimension_result()` mapper in `mappers.py`
3. Update `read_run_data()` to return `list[DimensionResult]`
4. Update `_load_evaluations()` and `_load_evidence_map()` to produce DTOs
5. Update all consumers:
   - `grades.summarize_dimensions(dims: list[DimensionResult])`
   - `dashboard._compute_dashboard_payload()`
   - `accumulated._read_all_run_data()`
   - `_dashboard_stale.collect_stale_dimensions()`
   - `_cache.make_lru_dimension_fetcher()`
6. Add `to_api_dict()` method on `DimensionResult` for API serialization
7. Remove `DimensionData` TypedDict from `shared/types.py`

**Breaking change boundary:** The `RunStorage` Protocol's `read_run_data` return type changes. Update the protocol and all implementations.

### Phase 2: Finding → Finding DTO

**Steps:**

1. Replace `FindingDict` TypedDict with `Finding` frozen dataclass
2. Update `build_finding_base()` → returns `Finding` instead of dict
3. Update `violations_parsing` to work with `Finding` objects
4. Update `json_parser._collect_findings()` to produce `Finding` tuples
5. Add `Finding.to_api_dict()` for serialization
6. Remove `FindingDict` from `shared/types.py`

### Phase 3: Report and Scoring DTOs

**Steps:**

1. `ParsedReport` TypedDict → `EvaluationReport` dataclass
2. `ScoringResult` TypedDict → `ScoringOutput` dataclass
3. `TotalsDict` → `Totals` dataclass (already shown above)
4. `DimensionSummary` → `DimensionsSummary` dataclass

### Phase 4: API response layer

**Steps:**

1. Create `src/quodeq/action_api_serializers.py` with explicit `to_json_dict()` functions
2. Update `action_api_routes.py` to call serializers before `jsonify()`
3. Remove all `.to_dict()` methods that produce raw dicts — replace with serializer functions
4. This is the only layer allowed to produce untyped dicts

---

## Design Rules

1. **DTOs are frozen dataclasses** — immutable after creation, no surprise mutations
2. **Tuples not lists** — DTO collections use `tuple[...]` for immutability; domain models can use `list` if they need mutation (e.g., `PrincipleEvidence` accumulates findings)
3. **Mappers are pure functions** — `parse_*(raw: dict) -> DTO` with no side effects; raise `ValueError` on invalid input
4. **Domain models own behavior** — `Evidence.compute_metrics()`, `PrincipleEvidence.compute_metrics()` stay as-is
5. **Serialization is explicit** — `to_api_dict()` or a dedicated serializer module, never implicit dict spreading
6. **TypedDicts become transition types** — keep `shared/types.py` during migration as the "interface" between old-dict and new-DTO code; remove types as their DTO replacement stabilizes

## Naming Convention

| Layer | Suffix | Example |
|-------|--------|---------|
| Raw JSON | (none) | `dict` from `json.loads()` |
| DTO (inbound) | (none, just the noun) | `Finding`, `DimensionResult`, `Totals` |
| Domain model | (none) | `Evidence`, `PrincipleEvidence`, `Judgment` |
| API response | `Response` suffix | `ViolationResponse`, `ProjectListResponse` |

---

## Migration Strategy

- **Parallel types:** During each phase, the DTO and TypedDict coexist. Functions accept both via overloads or Union. Tests cover both paths.
- **Inside-out:** Start at the parser layer (where JSON enters), work outward toward the API. Never convert the API response layer before the domain layer is clean.
- **One TypedDict at a time:** Each PR converts exactly one TypedDict to a dataclass, updates all consumers, and removes the TypedDict.
- **Feature flags:** Not needed — this is a pure refactor with no behavior change. Each phase is a series of type-only commits that don't change runtime behavior.

## Success Criteria

- Zero `TypedDict` in `shared/types.py` (all replaced by frozen dataclasses)
- Zero `json.loads()` result passed beyond the parser/adapter layer without mapping
- Every function parameter and return type is either a domain model, a DTO, or a primitive — never a raw dict
- Type checker (`mypy --strict` or `pyright`) passes with zero `Any` in production code
