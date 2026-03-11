<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="res/quodeq-logo-dark.svg" />
    <img src="res/quodeq-logo.svg" alt="Quodeq" width="340" />
  </picture>
</p>

<h2 align="center">quodeq</h2>

<p align="center">
  <em>quality code compass</em><br>
  <em>human aligned quode</em><br>
</p>

---

**AI-powered code quality analysis across every dimension that matters.**

Get actionable insights, not just metrics.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Node.js 18+ (auto-installed for dashboard)
- An AI CLI client (e.g. [Claude Code](https://docs.anthropic.com/en/docs/claude-code))

## Quick Start

### Install

```bash
uv sync
```

### Run the Dashboard

```bash
uv run quodeq dashboard
```

This will:
1. Install npm dependencies and build the web UI (first run only)
2. Start the Python Action API on an available port (default 8001)
3. Start the dashboard server on `http://localhost:4173`
4. Open your browser automatically

### Run an Evaluation

Evaluations can also be launched directly from the dashboard UI. If you want to run them without the dashboard:

```bash
# Evaluate a local repository (auto-detects language plugin)
uv run quodeq evaluate /path/to/your/project

# Evaluate a remote repository
uv run quodeq evaluate git@github.com:org/repo.git

# Evaluate specific dimensions only
uv run quodeq evaluate /path/to/project -d security,reliability

# Use a specific plugin
uv run quodeq evaluate /path/to/project -p typescript

# Evidence only (skip scoring)
uv run quodeq evaluate /path/to/project --evidence-only
```

### Configure AI Client

```bash
uv run quodeq configure
```

## CLI Reference

### `uv run quodeq evaluate`

| Flag | Default | Description |
|------|---------|-------------|
| `repo` | *(required)* | Path or URL to the repository |
| `-p, --plugin` | auto-detect | Plugin ID (typescript, python, kotlin, java, bash, mobile_ios) |
| `-o, --output` | `evaluations` | Reports output directory |
| `-m, --mode` | `numerical` | Scoring mode: `numerical` or `grades` |
| `-d, --dimensions` | all | Comma-separated dimensions to evaluate |
| `--evidence-only` | off | Produce evidence JSON only (skip scoring) |
| `--max-turns` | 200 | Max AI conversation turns per dimension |
| `--max-duration` | 1800 | Max seconds per dimension before terminating |
| `--no-prescan` | off | Skip source-file counting |

### `quodeq dashboard`

| Flag | Default | Description |
|------|---------|-------------|
| `--port` | 4173 | Dashboard server port |
| `--evaluations` | `evaluations` | Evaluations directory |
| `--open` | `true` | Open browser automatically (`false` to skip) |
| `--no-build` | off | Skip web UI build (requires `ui/web/dist`) |
| `--reinstall` | off | Force reinstall npm dependencies |
| `--api-host` | auto | Override Action API host |
| `--api-port` | auto | Override Action API port |
| `--static-dist` | `ui/web/dist` | Path to built dashboard assets |

## Supported Plugins

| Plugin | Languages / Frameworks |
|--------|----------------------|
| `typescript` | TypeScript, JavaScript |
| `python` | Python |
| `kotlin` | Kotlin |
| `java` | Java |
| `bash` | Bash, Shell |
| `mobile_ios` | Swift (iOS) |

Each plugin defines which dimensions apply and includes language-specific standards, knowledge bases, and prompt templates under `evaluators/<plugin>/`.

## Project Structure

```
quodeq/
  src/quodeq/               # Python package
    engine/                  # Evaluation engine (analysis, scoring, reporting)
    adapters/                # Report parsers, filesystem and web adapters
    config/                  # CLI configuration, knowledge refresh, standards
    dashboard/               # Dashboard server and UI build
    ports/                   # Abstract interfaces (Protocol-based)
    provider/                # Action provider (filesystem-backed implementation)
    shared/                  # Utilities, logging, paths, defaults
  evaluators/                # Language plugins (typescript, python, kotlin, java, bash, ios)
  standards/                 # ISO 25010, ASVS, CISQ standards with compiled CWE mappings
  prompts/                   # LLM prompt templates
  ui/web/                    # React + Vite dashboard
  evaluations/               # Evaluation output (generated)
  tools/                     # Standards compiler, migration scripts
  tests/                     # Test suite (mirrors src/ structure)
```

## Architecture

Quodeq uses a **ports and adapters** architecture:

- **Ports** (`ports/`) define abstract interfaces via Python `Protocol` classes
- **Adapters** (`adapters/`) implement those interfaces for filesystem, web, and hybrid backends
- **Engine** (`engine/`) orchestrates AI CLI analysis, stream parsing, evidence extraction, and scoring
- **Provider** (`provider/`) implements the Action API data layer with filesystem-backed storage

The evaluation pipeline:
1. **Plugin detection** — identifies the repository language and loads the matching evaluator
2. **Prompt building** — assembles standards, knowledge bases, and dimension-specific prompts
3. **AI analysis** — spawns the AI CLI with MCP tool server for real-time finding extraction
4. **Evidence collection** — findings stream as JSONL via MCP tool calls
5. **Scoring** — maps findings to ISO 25010 principles with CWE classifications
6. **Reporting** — produces per-dimension JSON reports with grades, violations, and compliance

## License

See [LICENSE](LICENSE).
