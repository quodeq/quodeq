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
