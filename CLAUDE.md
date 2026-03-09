# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

```bash
# Install dependencies
uv sync

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/engine/test_scoring.py

# Run a single test by name
uv run pytest tests/engine/test_scoring.py -k "test_name"

# Run the dashboard (builds UI on first run, starts API + web server)
uv run codecompass dashboard

# Run an evaluation
uv run codecompass evaluate /path/to/project

# Start the Action API in dev mode (for UI development)
uv run python -m codecompass.action_api

# UI dev server (separate terminal, after Action API is running)
cd ui/web && npm install && npm run dev

# UI tests
cd ui/web && node --test src/explorerUtils.test.js
```

## Architecture

### Evaluation Pipeline

The core flow when `codecompass evaluate` runs:

1. **Resolve repo** (`util/repo_handler.py`) — handles local paths or git clone URLs
2. **Detect plugin** (`engine/plugin_loader.py`) — matches file extensions/config files against `evaluators/<plugin_id>/plugin.json`
3. **Prescan** (`cli.py`) — counts source files for coverage tracking
4. **Per-dimension loop** (`engine/runner.py`) — for each dimension (security, reliability, etc.):
   - `prompt_builder.py` builds the prompt from `prompts/compass.md` template + standards checklist + plugin knowledge
   - `analysis.py` spawns an AI CLI subprocess with codebase tools (Read, Grep, Glob, Bash) and optionally an MCP findings server
   - Evidence is collected either via MCP tool calls (`mcp_findings.py` → JSONL file) or stream-JSON fallback parsing
   - `evidence_parser.py` deduplicates and groups findings by principle
5. **Merge** (`runner.py:_merge_evidence()`) — combines per-dimension evidence
6. **Score** (`scoring.py`) — compliance-based scoring with size-based scaling and violation penalties
7. **Report** (`report.py`) — writes `<plugin_id>.json` (dashboard) and `<plugin_id>_full.json` (detailed) to `evaluations/`

### Hexagonal Architecture (Ports & Adapters)

- **Ports** (`src/codecompass/ports/`) — abstract interfaces for evaluations, dimensions, practices, evaluators
- **ActionProvider** (`action_provider.py`) — runtime-checkable Protocol with sub-interfaces: ProjectActions, ReportActions, EvaluationActions, ToolingActions
- **Filesystem adapter** (`action_provider_fs.py`) — main implementation, reads from `evaluations/` directory
- **Web/Hybrid adapters** (`adapters/web/`, `adapters/hybrid/`) — alternative data sources

### MCP Findings Server

`engine/mcp_findings.py` implements a JSON-RPC 2.0 server over stdio using **newline-delimited JSON** (not Content-Length framing). It exposes a single `report_finding` tool that writes JSONL directly to a file as the AI calls it. Falls back to stream-JSON text extraction if MCP fails.

### Plugin System

Each plugin in `evaluators/<plugin_id>/` contains:
- `plugin.json` — id, name, file extension detection rules
- `dimensions.json` — which ISO 25010 dimensions apply, with weights
- `knowledge/practices.json` — practice definitions with CWE mappings, severity, principles
- `knowledge/analysis.md` — optional dimension-specific analysis guidance

Available plugins: typescript, python, kotlin, java, bash, mobile_ios. Cross-cutting practices in `evaluators/_cross_cutting/`.

### Standards

`standards/` contains ISO 25010, ASVS, and CISQ standards. `standards/compiled/` has pre-built CWE mappings per dimension. Tools in `tools/` (e.g., `compile_standards.py`, `resolve_practices.py`) maintain these.

### Web UI

React 18 + Vite + Recharts app in `ui/web/`. The dashboard runner (`dashboard/runner.py`) builds the UI, spawns the Flask Action API as a subprocess, and serves the built assets.

### Action API

Flask REST API (`action_api.py`) that proxies to an ActionProvider. Key endpoints under `/api/`: projects, dashboard data, accumulated scores, dimension evals, violations, evaluation jobs, plugins, and filesystem browsing.

## Key Conventions

- Python 3.12+, uses `uv` for package management and builds (`uv_build` backend)
- Entry point: `codecompass = "codecompass:main"` in `pyproject.toml` → `src/codecompass/__init__.py`
- Tests use pytest, located in `tests/` mirroring `src/` structure (engine tests in `tests/engine/`)
- No conftest.py files — fixtures are defined inline in test files
- The `_emit_marker()` pattern in `runner.py` sends structured JSON to stdout for job tracking in non-TTY mode
