<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="res/quodeq-logo-dark.svg" />
    <img src="res/quodeq-logo.svg" alt="Quodeq" width="340" />
  </picture>
</p>

<h2 align="center">The quality code compass</h2>
<p align="center"><em>Your guide to drive any codebase to excellence.</em></p>
<p align="center"><strong>v0.6.2</strong></p>

<p align="center">
  Quodeq scans any codebase with AI and scores it across six quality dimensions —
  <strong>Security</strong>, <strong>Reliability</strong>, <strong>Maintainability</strong>,
  <strong>Performance</strong>, <strong>Flexibility</strong>, and <strong>Usability</strong> —
  based on ISO 25010. Get grades, find violations, fix what matters.
</p>

---

## Requirements

| Dependency | Version | |
|---|---|---|
| [Python](https://www.python.org/downloads/) | 3.12+ | Runtime |
| [Node.js](https://nodejs.org/) | 18+ | Dashboard UI |
| [npm](https://www.npmjs.com/get-npm) | 9+ | Bundled with Node.js |
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | latest | AI analysis engine |

## Install

**Recommended:**
```bash
pipx install quodeq
```

**Homebrew:**
```bash
brew install quodeq/tap/quodeq
```

**pip:**
```bash
pip install quodeq
```

---

## Dashboard

The Quodeq Dashboard is the recommended way to use Quodeq. It lets you launch evaluations, browse results, and track quality over time — all from a single web UI.

```bash
quodeq dashboard
```

Opens at `http://localhost:4173` with:

- **Overall grade & score** — A-F letter grade, numeric score /10, trend across runs
- **Dimension breakdown** — individual scores per quality dimension with severity counts
- **Violations explorer** — drill into findings by file, principle, or CWE classification
- **Top offending files** — ranked list of where to focus remediation
- **Run history** — track how your codebase evolves over time

Click any dimension, file, or principle to explore the details.

### QuodeqBar (macOS)

On macOS, [**QuodeqBar**](https://github.com/quodeq/quodeq/releases/latest) lives in your menu bar and manages the dashboard for you — start/stop the server, see evaluation status at a glance, and open the dashboard in one click.

### CLI-only usage

You can also run evaluations directly from the terminal without the dashboard:

```bash
quodeq evaluate /path/to/project
```

Run `quodeq evaluate --help` for all options.

---

## The Q² Scoring Formula

Quodeq scores each principle on a 0–10 scale using four independent constraints:

1. **Violation Base** — hyperbolic curve where the first violations hurt most (`10 / (1 + K * weighted_violations)`)
2. **Compliance Lift** — evidence of good practices fills the gap between the base and 10
3. **Violation Ceiling** — log₂-based cap prevents compliance from overriding significant violations
4. **Severity Grade Floor** — grade labels match reality (only critical violations can produce a "Critical" grade)

The final score: `max(floor, min(ceiling, base + (10 - base) * lift))`

Full details in [src/quodeq/core/scoring/README.md](src/quodeq/core/scoring/README.md).

## Supported Languages

Quodeq can evaluate **any codebase in any language**. The AI analysis engine reads and understands code regardless of the tech stack.

## How It Works

1. **Detect** — identifies the languages and structure of the codebase
2. **Analyze** — spawns an AI CLI with read-only tools to explore the code
3. **Collect** — findings stream as structured JSONL via tool calls
4. **Score** — maps findings to ISO 25010 principles with CWE classifications
5. **Report** — produces per-dimension reports with grades, violations, and compliance

Results are stored in `~/.quodeq/evaluations/` and persist across sessions.

## CLI Reference

### `quodeq evaluate`

| Flag | Default | Description |
|------|---------|-------------|
| `repo` | *(required)* | Path or URL to the repository |
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
