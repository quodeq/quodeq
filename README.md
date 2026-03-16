<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="res/quodeq-logo-dark.svg" />
    <img src="res/quodeq-logo.svg" alt="Quodeq" width="340" />
  </picture>
</p>

<h2 align="center">AI-powered code quality evaluation</h2>

<p align="center">
  Evaluate any repository across six quality dimensions — <strong>Security</strong>, <strong>Reliability</strong>, <strong>Maintainability</strong>, <strong>Performance</strong>, <strong>Flexibility</strong>, and <strong>Usability</strong> — using LLM-driven analysis mapped to ISO 25010 and CWE classifications.
</p>

---

## Install

```bash
# Recommended
pipx install quodeq

# Or with Homebrew
brew install quodeq/tap/quodeq

# Or with pip
pip install quodeq
```

### From source (development)

```bash
git clone https://github.com/quodeq/quodeq.git
cd quodeq
uv sync
```

## Prerequisites

- Python 3.12+
- An AI CLI client (e.g. [Claude Code](https://docs.anthropic.com/en/docs/claude-code))
- Node.js 18+ *(only when installing from source — pre-built UI is bundled in pip/brew installs)*

## Usage

### Launch the dashboard

```bash
quodeq dashboard
```

Opens a web UI at `http://localhost:4173` where you can browse evaluations and launch new ones.

### Run an evaluation

```bash
# Local repository (auto-detects language)
quodeq evaluate /path/to/your/project

# Remote repository
quodeq evaluate git@github.com:org/repo.git

# Specific dimensions only
quodeq evaluate /path/to/project -d security,reliability

# Specific language plugin
quodeq evaluate /path/to/project -p typescript
```

### Configure AI client

```bash
quodeq configure
```

## CLI Reference

### `quodeq evaluate`

| Flag | Default | Description |
|------|---------|-------------|
| `repo` | *(required)* | Path or URL to the repository |
| `-p, --plugin` | auto-detect | Plugin ID (typescript, python, kotlin, java, bash, mobile_ios) |
| `-o, --output` | `~/.quodeq/evaluations` | Reports output directory |
| `-m, --mode` | `numerical` | Scoring mode: `numerical` or `grades` |
| `-d, --dimensions` | all | Comma-separated dimensions to evaluate |
| `--evidence-only` | off | Produce evidence JSON only (skip scoring) |
| `--max-turns` | 200 | Max AI conversation turns per dimension |
| `--max-duration` | 1800 | Max seconds per dimension |
| `--no-prescan` | off | Skip source-file counting |

### `quodeq dashboard`

| Flag | Default | Description |
|------|---------|-------------|
| `--port` | 4173 | Dashboard server port |
| `--evaluations` | `~/.quodeq/evaluations` | Evaluations directory |
| `--open` | true | Open browser automatically |
| `--no-build` | off | Skip web UI build |
| `--api-host` | auto | Override Action API host |
| `--api-port` | auto | Override Action API port |

## Supported Languages

| Plugin | Languages |
|--------|-----------|
| `typescript` | TypeScript, JavaScript |
| `python` | Python |
| `kotlin` | Kotlin |
| `java` | Java |
| `bash` | Bash, Shell |
| `mobile_ios` | Swift (iOS) |

## Environment Variables

All environment variables are optional. They override built-in defaults and, where noted, the corresponding CLI flags take precedence over env vars.

### API & Dashboard

| Variable | Default | Description |
|----------|---------|-------------|
| `QUODEQ_API_KEY` | *(none)* | API key for authenticating dashboard API requests. When unset, endpoints are unauthenticated |
| `QUODEQ_ACTION_API_PORT` | `8001` | Port for the Action API server |
| `QUODEQ_ACTION_API_HOST` | `127.0.0.1` | Host/IP the Action API binds to |
| `QUODEQ_DASHBOARD_PORT` | `4173` | Port for the dashboard preview server |
| `QUODEQ_STATIC_DIST` | *(bundled)* | Path to pre-built web UI assets (overrides the bundled `static/` directory) |
| `QUODEQ_EVALUATIONS_DIR` | `~/.quodeq/evaluations` | Directory where evaluation results are stored |
| `QUODEQ_RUN_DIR` | `~/.quodeq/run` | Directory for runtime files (PID file, etc.) |
| `QUODEQ_ALLOW_PLAINTEXT_HTTP` | *(off)* | Set to `1` to allow plaintext HTTP to non-localhost API hosts |
| `QUODEQ_MAX_PROJECTS_LISTED` | `200` | Maximum number of projects returned by the browse endpoint |
| `QUODEQ_MAX_ZIP_SIZE_MB` | `100` | Maximum zip export size in megabytes |

### AI Analysis

| Variable | Default | Description |
|----------|---------|-------------|
| `QUODEQ_AI_CLIENTS` | *(auto-detect)* | Comma-separated list of allowed AI CLI client IDs (e.g. `claude,codex`) |
| `QUODEQ_AI_TOOLS` | `Glob,Grep,Read` | Comma-separated list of tools enabled for the AI subprocess |
| `QUODEQ_AI_BASE_ARGS` | `--print --output-format stream-json --verbose` | Base CLI arguments passed to the AI subprocess |
| `QUODEQ_AI_CLI_TIMEOUT` | `300` | Timeout in seconds for AI CLI subprocess calls |
| `QUODEQ_SUBAGENT_MODEL` | *(client default)* | Model override for subagent analysis (omits `--model` when unset) |
| `QUODEQ_MAX_TURNS` | `200` | Maximum AI conversation turns per dimension (CLI flag `--max-turns` takes precedence) |
| `QUODEQ_MAX_DURATION` | `1800` | Maximum seconds per dimension (CLI flag `--max-duration` takes precedence) |

### Scoring & Evaluation

| Variable | Default | Description |
|----------|---------|-------------|
| `QUODEQ_CRITICAL_PENALTY` | `2.0` | Points deducted per critical violation type |
| `QUODEQ_MAJOR_PENALTY` | `1.0` | Points deducted per major violation type |
| `QUODEQ_MINOR_PENALTY` | `0.25` | Points deducted per minor violation type |
| `QUODEQ_DEFAULT_DIM_WEIGHT` | `1.0` | Default weight for quality dimensions during plugin scaffolding |
| `QUODEQ_SECURITY_DIM_WEIGHT` | `1.2` | Weight for the Security dimension |
| `QUODEQ_PERFORMANCE_DIM_WEIGHT` | `0.8` | Weight for the Performance dimension |
| `QUODEQ_MAX_VIOLATION_FILES` | `20` | Maximum number of violation files included in results |
| `QUODEQ_CWE_URL_TEMPLATE` | `https://cwe.mitre.org/data/definitions/{cwe_id}.html` | URL template for CWE references (`{cwe_id}` is replaced) |

### Caching

| Variable | Default | Description |
|----------|---------|-------------|
| `QUODEQ_RUN_DIM_CACHE_MAX` | `256` | Maximum entries in the run-dimension cache |
| `QUODEQ_ACC_CACHE_MAX` | `256` | Maximum entries in the accumulated-view cache |

### Knowledge Refresh & HTTP

| Variable | Default | Description |
|----------|---------|-------------|
| `QUODEQ_FETCH_TIMEOUT` | `15` | Timeout in seconds for knowledge-refresh HTTP fetches |
| `QUODEQ_CONTENT_SAMPLE_LIMIT` | `4000` | Character limit for content samples during knowledge refresh |
| `QUODEQ_MAX_FETCH_WORKERS` | `8` | Maximum concurrent worker threads for knowledge refresh |
| `QUODEQ_HTTP_TIMEOUT` | `10` | Default HTTP client timeout in seconds |
| `QUODEQ_HTTP_MAX_RETRIES` | `3` | Maximum HTTP retry attempts |
| `QUODEQ_HTTP_RETRY_DELAY` | `0.5` | Base delay in seconds between HTTP retries (exponential backoff) |
| `QUODEQ_HTTP_RETRY_JITTER` | `0.3` | Random jitter in seconds added to retry delays |
| `QUODEQ_CB_THRESHOLD` | `5` | Circuit breaker failure threshold (opens after N consecutive failures) |
| `QUODEQ_CB_RESET` | `60` | Circuit breaker reset time in seconds |
| `QUODEQ_ALLOW_PRIVATE_URLS` | *(off)* | Set to `1` to allow HTTP requests to private/internal addresses |
| `QUODEQ_GIT_CLONE_TIMEOUT` | `300` | Timeout in seconds for `git clone` operations |

### OWASP ASVS

| Variable | Default | Description |
|----------|---------|-------------|
| `QUODEQ_ASVS_URL` | *(GitHub raw URL)* | URL to the OWASP ASVS JSON file |
| `QUODEQ_ASVS_VERSION` | `4.0.3` | ASVS version string used for fetching standards |
| `QUODEQ_ASVS_SHA256` | *(none)* | Expected SHA-256 hash for ASVS integrity verification |
| `QUODEQ_GITHUB_SEARCH_URL` | `https://api.github.com/search/repositories` | GitHub API search endpoint |
| `QUODEQ_GITHUB_RAW_BASE_URL` | `https://raw.githubusercontent.com` | GitHub raw content base URL |

## How it works

1. **Plugin detection** — identifies the language and loads the matching evaluator
2. **Prompt building** — assembles standards, knowledge bases, and dimension-specific prompts
3. **AI analysis** — spawns the AI CLI with read-only tools for code exploration
4. **Evidence collection** — findings stream as JSONL via MCP tool calls
5. **Scoring** — maps findings to ISO 25010 principles with CWE classifications
6. **Reporting** — produces per-dimension reports with grades, violations, and compliance

Evaluations are stored in `~/.quodeq/evaluations/` and persist across sessions.

## Development

```bash
# Run tests
uv run pytest

# Start Action API (for UI dev)
uv run python -m quodeq.action_api

# Start dashboard in dev mode
cd ui/web && npm install && npm run dev
```

## License

See [LICENSE](LICENSE).
