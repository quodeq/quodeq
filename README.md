<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="res/quodeq-logo-dark.svg" />
    <img src="res/quodeq-logo.svg" alt="Quodeq" width="340" />
  </picture>
</p>

<h2 align="center">The quality code compass</h2>
<p align="center"><em>Your guide to drive any codebase to excellence.</em></p>
<p align="center"><strong>v1.0.0</strong></p>

<p align="center">
  Quodeq scans any codebase with AI and scores it across six quality dimensions --
  <strong>Security</strong>, <strong>Reliability</strong>, <strong>Maintainability</strong>,
  <strong>Performance</strong>, <strong>Flexibility</strong>, and <strong>Usability</strong> --
  based on ISO 25010. Get grades, find violations, fix what matters.
</p>

<p align="center">
  <a href="https://www.youtube.com/watch?v=YUq9cr__2CI">Watch the demo</a> · <a href="https://quodeq.ai">Website</a> · <a href="https://github.com/quodeq/quodeq/releases/latest">Releases</a>
</p>

---

> **Why now?** AI models can now autonomously find and exploit zero-day vulnerabilities across operating systems, browsers, and web applications. Thousands of previously unknown flaws have been uncovered in weeks, not years. The code you ship today will be read by models that can spot what humans miss. If your codebase carries security debt, reliability gaps, or maintenance shortcuts, the window to fix them is shrinking fast. Quodeq helps you prepare your software -- find what's wrong, enforce quality standards, and harden your code before the next generation of models is used against it.

---

## Getting Started

```bash
pipx install quodeq    # Install quodeq
quodeq dashboard       # Launch the dashboard
```

That's it. The dashboard lets you point to any project and run evaluations from the UI.

> Also available via `pip install quodeq`, or download the [macOS DMG](https://github.com/quodeq/quodeq/releases/latest) / [Windows installer](https://github.com/quodeq/quodeq/releases/latest) from Releases.

### Requirements

| Dependency | Version | |
|---|---|---|
| [Python](https://www.python.org/downloads/) | 3.12+ | Runtime (`brew install python` or [download](https://www.python.org/downloads/)) |
| [Node.js](https://nodejs.org/) | 18+ | Dashboard UI (`brew install node` or [download](https://nodejs.org/)) |

### AI Providers

Quodeq works with **local models** and **cloud AI CLIs**. Choose what fits your workflow:

#### Local models (free, private, your code never leaves your machine)

| Provider | Setup |
|---|---|
| [Ollama](https://ollama.com) | `ollama pull gemma3:27b` -- then select Ollama in Settings |

#### Cloud CLI providers (faster, deeper analysis)

| Provider | Setup |
|---|---|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | `npm i -g @anthropic-ai/claude-code` |
| [Codex CLI](https://github.com/openai/codex) | `npm i -g @openai/codex` |
| [Gemini CLI](https://github.com/google-gemini/gemini-cli) | `npm i -g @anthropic-ai/gemini-cli` |

After installing a CLI provider, go to **Settings** in the dashboard and select it. Quodeq auto-detects installed providers.

> **Tip:** For local models, `gemma3:27b` offers an excellent quality-to-cost ratio. For cloud, Claude Sonnet gives the best balance of speed, quality, and cost.

---

## Dashboard

The Quodeq Dashboard is the main way to use Quodeq. Launch evaluations, browse results, and track quality over time.

```bash
quodeq dashboard
```

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="res/dashboard-dark.png" />
    <img src="res/dashboard.png" alt="Quodeq Dashboard" width="900" />
  </picture>
</p>

Opens at `http://localhost:4173` with:

- **Overall grade and score** -- A-F letter grade, numeric score /10, trend across runs
- **Dimension breakdown** -- individual scores per quality dimension with severity counts
- **Violations explorer** -- drill into findings by file, principle, or CWE classification
- **Code map** -- visual heatmap of your codebase showing where issues concentrate
- **Top offending files** -- ranked list of where to focus remediation
- **Run history** -- track how your codebase evolves over time
- **Custom standards** -- create your own evaluation dimensions or import from the library

Click any dimension, file, or principle to explore the details. Dismiss false positives directly from the UI. Dismissed findings are excluded from future evaluations.

### QuodeqBar (macOS)

A native menu bar companion app to manage the dashboard. Start/stop the server, see evaluation status at a glance, and open the dashboard in one click.

> Download the DMG from [Releases](https://github.com/quodeq/quodeq/releases/latest). Since it's not yet signed, on first launch right-click the app, then click **Open** in the dialog.

### CLI usage

You can also run evaluations directly from the terminal:

```bash
quodeq evaluate /path/to/project
quodeq evaluate /path/to/project --scope src/api    # Scoped to a subdirectory
quodeq evaluate /path/to/project -d security        # Single dimension
```

Run `quodeq evaluate --help` and `quodeq dashboard --help` for all available options.

---

## How It Works

1. **Detect** -- identifies the languages and structure of the codebase
2. **Analyze** -- sends an AI agent with read-only tools to explore the code
3. **Collect** -- findings stream as structured JSONL via tool calls
4. **Score** -- maps findings to ISO 25010 principles with CWE classifications
5. **Report** -- produces per-dimension reports with grades, violations, and compliance

Results are stored in `~/.quodeq/evaluations/` and persist across sessions.

## Standards

By default, Quodeq evaluates six quality dimensions based on **ISO 25010**: Security, Reliability, Maintainability, Performance, Flexibility, and Usability.

It also ships with additional built-in standards:

- **Clean Architecture** -- dependency rules, layer boundaries, separation of concerns
- **Domain-Driven Design** -- bounded contexts, aggregates, ubiquitous language

You can **create your own standards** from the dashboard, or ask any AI to generate one as a `.json` file and import it. See the Help tab in the dashboard for the full schema.

## Supported Languages

Quodeq can evaluate **any codebase in any language**. The AI analysis engine reads and understands code regardless of the tech stack.

---

## The Q² Scoring Formula

Quodeq scores each principle on a 0-10 scale using four independent constraints:

1. **Violation Base** -- hyperbolic curve where the first violations hurt most (`10 / (1 + K * weighted_violations)`)
2. **Compliance Lift** -- evidence of good practices fills the gap between the base and 10
3. **Violation Ceiling** -- log-based cap prevents compliance from overriding significant violations
4. **Severity Grade Floor** -- grade labels match reality (only critical violations can produce a "Critical" grade)

The final score: `max(floor, min(ceiling, base + (10 - base) * lift))`

Full details in [src/quodeq/core/scoring/README.md](src/quodeq/core/scoring/README.md).

## Development

```bash
git clone https://github.com/quodeq/quodeq.git && cd quodeq
uv sync
uv run pytest
```

### Built with Claude Code

Development powered by [Claude Code](https://claude.ai/code) from [Anthropic](https://anthropic.com).

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

## License

See [LICENSE](LICENSE).
