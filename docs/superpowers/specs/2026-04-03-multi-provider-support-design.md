# Multi-Provider Support Design

**Date:** 2026-04-03
**Status:** Draft
**Goal:** Make Quodeq model-agnostic — support any CLI tool and any LLM API with minimal code changes.

## Motivation

Quodeq's mission is to preserve human coding standards regardless of who — or what — writes the code. To fulfill that mission, the tool cannot be locked to a single LLM provider. It must be accessible to everyone: beginners using local models, companies with existing contracts, researchers evaluating synthetic code across providers.

The current architecture delegates all LLM work to a CLI tool (Claude Code, Codex) via subprocess. This design extends that approach with a second execution path for direct API access, keeping the existing pipeline intact.

## Architecture: Dual-Mode Execution

Two runner types share a single output contract (JSONL evidence):

```
quodeq evaluate
  → build prompt
  → provider type?
      ├── CLI runner (existing) → subprocess: claude/codex/gemini/aider → stream-json + MCP
      └── API runner (new)      → OpenAI SDK → structured JSON output
  → both produce JSONL evidence
  → scoring → report (unchanged)
```

### CLI Runner (existing, extended)

Spawns an external CLI tool as a subprocess. The CLI tool acts as a full agent with multi-turn reasoning, file exploration, and MCP tool use. This is the "full power" path.

**Currently supported:** Claude Code, Codex CLI
**To add:** Gemini CLI, Aider, OpenCode, GitHub Copilot CLI, Pi

Each CLI tool is configured in `ai_providers.json` with `"type": "cli"` and its specific args/env.

### API Runner (new)

Calls any OpenAI-compatible API directly using the OpenAI Python SDK. Quodeq pre-loads the source files into the prompt context and requests structured JSON output. This is the "universal" path for providers that don't have a CLI tool, including local models.

**Supported via OpenAI-compatible API:** Ollama, OpenRouter, LM Studio, vLLM, Together, Groq, Mistral, DeepSeek, any OpenAI-compatible endpoint.

**Why OpenAI SDK (not LiteLLM):** The OpenAI-compatible API has become the de facto standard — nearly every provider implements it. Using the OpenAI SDK directly means one small, well-maintained dependency instead of a large transitive dependency tree. LiteLLM was considered but rejected due to a recent supply chain attack (March 2026) and the principle of minimizing the trust surface.

### Output Contract

Both runners produce JSONL files with identical schema. Each line is a finding:

**Required fields:**
- `req` (string): Requirement ID (e.g., `"M-MOD-1"`)
- `t` (string): `"violation"` or `"compliance"`
- `file` (string): File path relative to repo root
- `line` (integer): Line number
- `severity` (string): `"critical"`, `"major"`, or `"minor"`
- `w` (string): Short description/title
- `reason` (string): Why this is a violation or compliance

**Optional fields:** `p`, `d`, `end_line`, `scope`, `snippet`, `vt`, `context`, `refs`

Both runners pass output through the existing `FindingsRouter` for enrichment (adding `schema_version`, `req_refs`, resolving dimensions). No duplication of enrichment logic.

## Provider Configuration

### ai_providers.json

Each provider declares its `type` (`"cli"` or `"api"`) which determines the runner:

```json
{
  "claude": {
    "type": "cli",
    "cmd": "claude",
    "base_args": "--print --output-format stream-json --verbose",
    "mcp_permission_args": ["--permission-mode", "bypassPermissions"],
    "env_set_if_missing": {"CODEX_SANDBOX": "read-only"},
    "env_remove": ["CLAUDECODE"]
  },
  "codex": {
    "type": "cli",
    "cmd": "codex",
    "base_args": "--print --output-format stream-json --verbose",
    "mcp_permission_args": [],
    "env_set_if_missing": {"CODEX_SANDBOX": "read-only"}
  },
  "gemini": {
    "type": "cli",
    "cmd": "gemini",
    "base_args": "--to-be-determined",
    "mcp_permission_args": []
  },
  "aider": {
    "type": "cli",
    "cmd": "aider",
    "base_args": "--to-be-determined",
    "mcp_permission_args": []
  },
  "ollama": {
    "type": "api",
    "model": "llama3.1",
    "api_base": "http://localhost:11434/v1"
  },
  "openrouter": {
    "type": "api",
    "model": "anthropic/claude-sonnet-4",
    "api_key_env": "OPENROUTER_API_KEY"
  },
  "custom": {
    "type": "api",
    "model": "${AI_MODEL}",
    "api_base": "${AI_API_BASE}",
    "api_key_env": "AI_API_KEY"
  }
}
```

Notes:
- CLI providers with `"base_args": "--to-be-determined"` will be filled in as each CLI tool is integrated.
- The `"custom"` entry is the escape hatch for power users — `${VAR}` placeholders are resolved at runtime from environment variables (same as `.quodeq.env` sourcing).
- `api_key_env` names the environment variable holding the API key (never stored in JSON).

### .quodeq.env

Persistent user config, written by `quodeq configure`:

```bash
# Provider
export AI_PROVIDER=openrouter
export OPENROUTER_API_KEY=sk-or-...

# Model tiers (optional — omit to use AI_MODEL for everything)
export QUODEQ_MODEL_ORCHESTRATOR=claude-haiku
export QUODEQ_MODEL_LIGHT=claude-haiku
export QUODEQ_MODEL_MEDIUM=claude-sonnet-4
export QUODEQ_MODEL_HIGH=claude-opus-4

# Single model override (overrides all tiers)
# export AI_MODEL=my-model
```

## Model Tiers

Four roles allow cost optimization and capability matching:

| Tier | Purpose | Needs |
|------|---------|-------|
| **Orchestrator** | Routes tasks, plans analysis | Reasoning, low cost |
| **Light** | Quick scans, syntax checks, simple patterns | Speed, low cost |
| **Medium** | Standard evaluation — most dimensions | Good reasoning, decent context |
| **High** | Deep analysis — security audits, architecture | Best reasoning, large context |

**Defaults and backward compatibility:**
- If only `AI_MODEL` is set, it's used for all tiers. Zero friction.
- Tiers are opt-in. Setting `QUODEQ_MODEL_MEDIUM` overrides only the medium tier.
- If no tiers are configured, the provider's default model is used for everything.
- `AI_MODEL` overrides all tiers when set (escape hatch for single-model setups).

**Configuration surfaces:**
- `quodeq configure --models` — interactive CLI wizard
- Dashboard Settings panel — dropdown per tier
- Environment variables — direct control for CI/CD

## Configuration UX

### Tier 1: Easy Mode — `quodeq configure --ai-cli`

Interactive wizard for beginners:

1. Show available providers grouped by type (CLI Tools / API Providers)
2. For CLI tools: show install instructions, verify the command is available
3. For API providers: ask for model name, endpoint URL, API key (if needed)
4. Write to `.quodeq.env`

### Tier 2: Power Mode — env vars + JSON

For companies, CI/CD, researchers:
- Set `AI_PROVIDER`, `AI_MODEL`, `AI_API_BASE` etc. as environment variables
- Add custom providers to `ai_providers.json`
- Override per-run: `quodeq evaluate --model my-model ./src`

### Dashboard Settings

The web UI Settings panel exposes:
- Provider selection (dropdown)
- Model tier configuration (dropdown per tier, populated from provider's available models)
- API base URL and key fields (for API providers)
- Save/reset buttons
- Changes write to `.quodeq.env` via the existing API

## Files Changed

### Modified (small changes)
- `ai_providers.json` — add `type` field, new provider entries
- `ai_provider.py` — expand `PROVIDERS` dict, support new providers
- `_provider_cache.py` — parse `type` field, updated fallbacks
- `_command.py` — route to correct runner based on provider type
- `subprocess.py` or `runner.py` — dispatch: CLI → existing path, API → new runner
- `shared/defaults.json` — add model tier defaults
- `shared/utils.py` — add model tier env var accessors
- `services/tooling_mixin.py` — extend model fetching for non-Anthropic providers
- Dashboard Settings component — add provider/tier dropdowns

### New files
- `analysis/_api_runner.py` — OpenAI SDK-based runner. Pre-loads code context, calls API, parses structured JSON response, writes JSONL evidence, passes through `FindingsRouter`.
- `analysis/_api_prompt.py` — Prompt assembly for direct API mode. Bundles source files + standards + evaluation instructions into a single prompt with structured output instructions.
- `config/ai_models.py` — Model tier resolution logic. Reads `QUODEQ_MODEL_*` env vars, falls back to `AI_MODEL`, falls back to provider default.

### Unchanged
- Scoring engine (`engine/`)
- Report generation
- Evidence model and parser (`core/evidence/`)
- Standards and evaluators (`data/`)
- MCP findings server (still used by CLI runners)
- Dashboard (except Settings panel)

## API Runner Detail

### Prompt Assembly (`_api_prompt.py`)

The API runner cannot explore files interactively like a CLI agent. Instead, Quodeq pre-loads the context:

1. Read the source files targeted for evaluation (already known from the manifest/queue)
2. Load the compiled standards for the dimension being evaluated
3. Assemble into a single prompt: system instructions + standards + code + output format
4. Request `response_format: {"type": "json_object"}` for structured output

The prompt includes the JSONL schema so the model knows exactly what fields to produce.

### Execution Flow (`_api_runner.py`)

```python
# Pseudocode
client = openai.OpenAI(base_url=provider.api_base, api_key=api_key)
response = client.chat.completions.create(
    model=provider.model,
    messages=[{"role": "user", "content": assembled_prompt}],
    response_format={"type": "json_object"},
    temperature=0.1,
)
findings = parse_findings(response.choices[0].message.content)
write_jsonl(findings, jsonl_file)
enrich_via_findings_router(jsonl_file)
```

### Limitations vs CLI Runner

The API runner is inherently less capable than CLI agents:
- No multi-turn file exploration — Quodeq must pre-load all relevant files
- Limited by context window — very large codebases may need chunking
- No MCP tool use — findings come from structured output, not tool calls
- Model quality varies — smaller local models may produce lower-quality findings

These are acceptable trade-offs for universality. The CLI tools remain the recommended path for comprehensive analysis.

## Phasing

### Phase 1: Foundation
- Add `type` field to provider config
- Implement API runner with OpenAI SDK
- Add Ollama and OpenRouter as built-in API providers
- Model tier env vars and resolution logic
- `quodeq configure --models` wizard

### Phase 2: CLI Expansion
- Add Gemini CLI adapter (args, output parsing)
- Add Aider adapter
- Add OpenCode adapter
- Normalize output format differences between CLI tools

### Phase 3: Dashboard & Polish
- Settings panel for provider + model tier selection
- Model discovery (list available models from provider)
- Per-evaluation model override in dashboard
- Documentation and guides

## Success Criteria

- A user with only Ollama installed can run `quodeq configure`, pick Ollama, and evaluate code
- A user with OpenRouter can evaluate with any model available on the platform
- CLI tools (Claude Code, Codex) continue working exactly as before
- The scoring engine produces identical report structure regardless of provider
- `AI_MODEL` single-model setups continue working with no config changes (backward compatible)
