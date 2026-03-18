<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="res/quodeq-logo-dark.svg" />
    <img src="res/quodeq-logo.svg" alt="Quodeq" width="340" />
  </picture>
</p>

<h3 align="center">AI-powered code quality analysis mapped to ISO 25010 & CWE</h3>

<p align="center">
  Point Quodeq at any repo and get a full quality breakdown across
  <strong>Security</strong>, <strong>Reliability</strong>, <strong>Maintainability</strong>,
  <strong>Performance</strong>, <strong>Flexibility</strong>, and <strong>Usability</strong> —
  with grades, scores, violations, and actionable findings.
</p>

---

## Dashboard

The Quodeq Dashboard is where everything comes together. Launch it with:

```bash
quodeq dashboard
```

You get a live web UI at `http://localhost:4173` with:

- **Overall grade & score** — A-F letter grade, numeric score /10, trend across runs
- **Dimension breakdown** — individual scores per quality dimension with severity counts
- **Violations explorer** — drill into findings by file, principle, or CWE classification
- **Top offending files** — ranked list of where to focus remediation
- **Run history** — track how your codebase evolves over time

Click any dimension, file, or principle to explore the details.

### QuodeqBar (macOS)

On macOS, **QuodeqBar** lives in your menu bar and manages the dashboard for you — start/stop the server, see evaluation status at a glance, and open the dashboard in one click. Just open the app and it handles the rest.

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

**Requirements:** Python 3.12+ and an AI CLI client (e.g. [Claude Code](https://docs.anthropic.com/en/docs/claude-code)).
Node.js 18+ is only needed when installing from source.

## Quick Start

```bash
# Configure your AI client
quodeq configure

# Evaluate a local project
quodeq evaluate /path/to/your/project

# Evaluate a remote repo
quodeq evaluate git@github.com:org/repo.git

# Specific dimensions only
quodeq evaluate /path/to/project -d security,reliability

# Open the dashboard
quodeq dashboard
```

## How It Works

1. **Detect** — identifies the language and loads the matching evaluator plugin
2. **Analyze** — spawns an AI CLI with read-only tools to explore the codebase
3. **Collect** — findings stream as structured JSONL via tool calls
4. **Score** — maps findings to ISO 25010 principles with CWE classifications
5. **Report** — produces per-dimension reports with grades, violations, and compliance

Results are stored in `~/.quodeq/evaluations/` and persist across sessions.

## Supported Languages

TypeScript/JavaScript, Python, Kotlin, Java, Bash/Shell, Swift (iOS)

## CLI Reference

### `quodeq evaluate`

| Flag | Default | Description |
|------|---------|-------------|
| `repo` | *(required)* | Path or URL to the repository |
| `-p, --plugin` | auto-detect | Plugin ID (typescript, python, kotlin, java, bash, mobile_ios) |
| `-o, --output` | `~/.quodeq/evaluations` | Reports output directory |
| `-d, --dimensions` | all | Comma-separated dimensions to evaluate |
| `--max-turns` | 200 | Max AI conversation turns per dimension |
| `--max-duration` | 1800 | Max seconds per dimension |

### `quodeq dashboard`

| Flag | Default | Description |
|------|---------|-------------|
| `--port` | 4173 | Dashboard server port |
| `--evaluations` | `~/.quodeq/evaluations` | Evaluations directory |
| `--open` | true | Open browser automatically |

## Development

```bash
git clone https://github.com/quodeq/quodeq.git && cd quodeq
uv sync
uv run pytest
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

## License

See [LICENSE](LICENSE).
