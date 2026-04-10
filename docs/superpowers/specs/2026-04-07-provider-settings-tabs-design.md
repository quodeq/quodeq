# Provider Settings Tabs

## Goal

Replace the flat Analysis settings section with tabbed per-provider configuration. Each provider (Ollama, Claude Code, OpenRouter) gets its own tab with independent settings. Ollama tab includes server status, model discovery from installed models, and automatic agent count detection.

## Architecture

### Tab Structure

The Settings page's Analysis section becomes a tabbed panel. Tabs are dynamically generated from detected providers (the existing `GET /api/ai-clients` endpoint). Each tab renders the same settings form but with its own persisted state.

```
[● Ollama]  [● Claude Code]  [● OpenRouter]
┌─────────────────────────────────────────────┐
│  Server status: ● Running (localhost:11434)  │  ← Ollama only
│                                              │
│  Model:        [gemma4:26b         ▾]        │  ← dropdown for Ollama, text+suggestions for CLI, text+link for cloud
│                                              │
│  Analysis models:                            │
│  Fast:     [Click to select  ]               │
│  Balanced: [gemma4:26b       ]               │
│  Thorough: [Click to select  ]               │
│                                              │
│  Max agents:  [1]  [Auto-detect]             │  ← VRAM estimate default, test button refines
│                                              │
│  Time limit:  [Per-dimension ▪ Grouped]      │
│               [Unlimited ▪ Limited] [∞]      │
│                                              │
│  Verify findings: [On ▪ Off]                 │
└─────────────────────────────────────────────┘
```

The green/red dot next to each tab name indicates whether the provider is reachable. For Ollama, this means the server is running. For CLI tools, it means the binary is found on PATH. For cloud APIs, it's based on the last connection test (or untested = grey).

### Provider Types

**Ollama (type: api, local):**
- Server status banner: green when running, red with "Run `ollama serve` or open the Ollama app" when offline
- Model selector: dropdown populated by `GET /api/ollama/models` (proxies `ollama list`)
- Model tiers: same dropdown, pick from installed models for each tier
- Agent auto-detect: on model selection, estimate from VRAM (`model size / available GPU memory`). Test button sends concurrent requests to measure actual throughput.
- Default: 1 agent, unlimited time, per-dimension

**CLI tools — Claude Code, Codex, Gemini CLI, etc. (type: cli):**
- No server status (binary detection only, via existing `GET /api/ai-clients`)
- Model selector: text input with autocomplete suggestions from `data/config/known_models.json`
- Model tiers: same text input with suggestions
- No agent auto-detect (default 1)
- Default: 1 agent, 10 min time limit, per-dimension

**Cloud API — OpenRouter, custom (type: api, remote):**
- No server status banner
- Model selector: text input + "Browse models" link to provider's model catalog
- Test button: verifies API key + model work (sends a minimal completion request)
- No agent auto-detect (default 1)
- Default: 1 agent, 10 min time limit, per-dimension

### Per-Provider Settings State

Each setting is keyed by provider ID in localStorage:

```
cc-{providerId}-model          → "gemma4:26b"
cc-{providerId}-model-fast     → "gemma4:e4b"
cc-{providerId}-model-balanced → "gemma4:26b"
cc-{providerId}-model-thorough → "gemma4:31b"
cc-{providerId}-subagents      → "3"
cc-{providerId}-pool-budget    → "0" (0 = unlimited)
cc-{providerId}-per-dimension  → "true"
cc-{providerId}-verify         → "true"
```

The active provider tab ID is stored as `cc-active-provider`. When starting an evaluation, settings are read from the active provider's keys.

### Global Settings (unchanged)

- Theme mode (light/dark/system)
- Theme family (daruma/neo/ifrit/deckard/galadriel)
- Analysis power level (fast/balanced/thorough) — maps to the active provider's tier models

## LLM Bridge Module

All provider interaction logic lives in a new `llm_bridge` module — clean separation between the analysis engine and LLM provider details.

```
src/quodeq/llm_bridge/
  __init__.py          ← public API: status(), models(), test(), estimate_agents()
  _ollama.py           ← Ollama-specific: server status, model list, VRAM, concurrency test
  _cloud.py            ← Cloud API: connection test, model validation
  _models.py           ← known_models.json loading, model suggestions per CLI provider
  _providers.py        ← provider detection, reachability check, type classification
```

**Boundary rule:** The analysis layer and API routes call `llm_bridge` functions. They never talk to Ollama/OpenRouter/etc. directly. The bridge returns clean data structures, not raw HTTP responses.

**What moves here from existing code:**
- Provider config loading (`_provider_cache.py`) → `_providers.py`
- Ollama detection (`_is_ollama`, URL handling) → `_ollama.py`
- Provider type resolution (`_get_provider_type`) → `_providers.py`

**What stays in the analysis layer:**
- Prompt assembly (`api_prompt_assembly.py`)
- Instructor/Pydantic schema (`_api_runner.py`)
- Finding enrichment, file queue, subagent pool

### Public API

```python
from quodeq.llm_bridge import (
    get_provider_status,     # → {"running": bool, "version": str, ...}
    list_ollama_models,      # → [{"name": "gemma4:26b", "size": ..., ...}]
    estimate_max_agents,     # → {"estimate": 3, "model_size": 34e9, "gpu_memory": 48e9}
    test_concurrency,        # → {"recommended": 3, "results": [...]}
    test_cloud_connection,   # → {"success": bool, "latency_ms": int, "error": str}
    get_known_models,        # → {"claude": [{"id": ..., "label": ..., "tier": ...}]}
    get_provider_configs,    # → {"ollama": {"type": "api", ...}, "claude": {"type": "cli", ...}}
)
```

## New API Routes

Flask routes in `api/llm_bridge_routes.py` — thin wrappers around the `llm_bridge` module.

### `GET /api/ollama/status`

Check if Ollama server is running.

Response:
```json
{"running": true, "version": "0.20.2", "address": "localhost:11434"}
```
or
```json
{"running": false, "error": "Connection refused"}
```

Implementation: `llm_bridge.get_provider_status("ollama")` — HTTP HEAD to `http://localhost:11434` with 2s timeout.

### `GET /api/ollama/models`

List installed Ollama models.

Response:
```json
{
  "models": [
    {"name": "gemma4:26b", "size": 34088653984, "quantization": "Q4_K_M", "family": "gemma4"},
    {"name": "gemma4:e4b", "size": 14000000000, "quantization": "Q4_K_M", "family": "gemma4"}
  ]
}
```

Implementation: `llm_bridge.list_ollama_models()` — proxies `GET http://localhost:11434/api/tags`.

### `POST /api/ollama/test-concurrency`

Run a timing test to find optimal parallel agents.

Request:
```json
{"model": "gemma4:26b"}
```

Response:
```json
{
  "recommended": 3,
  "results": [
    {"agents": 1, "avg_ms": 2100, "status": "ok"},
    {"agents": 2, "avg_ms": 2800, "status": "ok"},
    {"agents": 3, "avg_ms": 3200, "status": "ok"},
    {"agents": 4, "avg_ms": 8500, "status": "degraded"},
    {"agents": 5, "avg_ms": null, "status": "failed"}
  ],
  "vram_estimate": 3
}
```

Implementation: `llm_bridge.test_concurrency(model)` — sends concurrent small completions, measures latency per level. VRAM estimate from `llm_bridge.estimate_max_agents(model)`.

### `POST /api/provider/test`

Test a cloud API provider connection.

Request:
```json
{"provider": "openrouter", "model": "qwen/qwen3.6-plus-preview:free", "api_base": "https://openrouter.ai/api/v1", "api_key": "sk-..."}
```

Response:
```json
{"success": true, "model": "qwen/qwen3.6-plus-preview:free", "latency_ms": 450}
```
or
```json
{"success": false, "error": "401 Unauthorized — check your API key"}
```

Implementation: `llm_bridge.test_cloud_connection(provider, model, api_base, api_key)` — minimal chat completion with `max_tokens=1`.

## New Data File

### `data/config/known_models.json`

Hardcoded model suggestions for CLI providers. Ships with the package, updated on quodeq releases.

```json
{
  "claude": {
    "models": [
      {"id": "claude-haiku-4-5-20251001", "label": "Haiku 4.5", "tier": "fast"},
      {"id": "claude-sonnet-4-6-20260407", "label": "Sonnet 4.6", "tier": "balanced"},
      {"id": "claude-opus-4-6-20260407", "label": "Opus 4.6", "tier": "thorough"}
    ]
  },
  "codex": {
    "models": [
      {"id": "gpt-4o-mini", "label": "GPT-4o Mini", "tier": "fast"},
      {"id": "gpt-4o", "label": "GPT-4o", "tier": "balanced"},
      {"id": "o3", "label": "o3", "tier": "thorough"}
    ]
  },
  "gemini-cli": {
    "models": [
      {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash", "tier": "fast"},
      {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro", "tier": "thorough"}
    ]
  }
}
```

## UI Components

### New Components

- `ProviderTabs` — tab bar with status dots, renders active tab's content
- `OllamaTab` — server status + model dropdown + settings
- `CliProviderTab` — model input with suggestions + settings
- `CloudProviderTab` — model input with link + test button + settings
- `ProviderSettings` — shared settings form (agents, time limit, mode, verify)
- `ModelDropdown` — click-to-select dropdown for Ollama models
- `ModelSuggestInput` — text input with autocomplete suggestions
- `AgentDetector` — VRAM estimate display + test button
- `ServerStatus` — green/red banner for Ollama

### Modified Components

- `SettingsPage` — replace current `ModelSection` + `AnalysisSection` with `ProviderTabs`
- `useEvaluation.js` — read settings from active provider's localStorage keys

### Removed Components

- `ModelSection` — replaced by provider-specific model selection in each tab
- `ClientSelector` — replaced by tab bar

## Data Flow

1. Settings page loads → `GET /api/ai-clients` returns available providers
2. For each provider, check reachability (Ollama: `/api/ollama/status`, CLI: already known from ai-clients, Cloud: last test result from localStorage)
3. Render tabs with status dots
4. Active tab loads its settings from `cc-{providerId}-*` localStorage keys
5. User changes settings → saved to provider-specific localStorage keys
6. User starts evaluation → `useEvaluation` reads active provider's settings and builds the API payload

## Migration

On first load after update, if per-provider keys don't exist but old global keys do (`cc-max-subagents`, `cc-pool-budget`, etc.), copy old values to the active provider's keys. Delete old global keys after migration.

## Error Handling

- Ollama offline: show red banner with instructions, disable model selector and test button
- Ollama model list fails: show "Could not load models" with retry button
- Concurrency test fails: show result up to the point of failure, keep VRAM estimate
- Cloud API test fails: show error message (401, timeout, model not found)
- No providers detected: show setup guide with links to install CLI tools or configure API providers
