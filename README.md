<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="res/quodeq-logo-dark.svg" />
    <img src="res/quodeq-logo.svg" alt="Quodeq" width="340" />
  </picture>
</p>

<h2 align="center">The quality code compass</h2>
<p align="center"><em>Your guide to drive any codebase to excellence.</em></p>
<p align="center"><strong>v1.0.3</strong></p>

<p align="center">
  <a href="https://www.youtube.com/watch?v=C9feqpR5BMI&list=PLJjpl8sE7W-U1HMePWdGis7w834NPYD3R">Watch the 2-min demo</a> · <a href="https://quodeq.ai">Website</a> · <a href="https://quodeq.ai/blog/">Blog</a> · <a href="https://github.com/quodeq/quodeq/releases/latest">Releases</a>
</p>

---

### Why

AI models can now autonomously find and exploit zero-day vulnerabilities across operating systems, browsers, and web applications. Thousands of previously unknown flaws have been uncovered in weeks, not years. The code you ship today will be read by models that can spot what humans miss.

But the tools to prepare for this are locked behind enterprise contracts and partner programs. Quodeq exists to change that.

**Open source. MIT license. Runs locally. No telemetry. No account. No servers.**

Quodeq scans any codebase with AI and scores it across six quality dimensions based on [ISO 25010](https://www.iso.org/standard/35733.html): **Security**, **Reliability**, **Maintainability**, **Performance**, **Flexibility**, and **Usability**. Every finding maps to a [CWE](https://cwe.mitre.org/) identifier. You get grades, violations with line numbers, and a fix plan.

You choose how it runs. Cloud providers (Claude, Gemini, Codex) for speed. Local models via [Ollama](https://ollama.com) for privacy. Your code, your choice.

---

## What It Finds

Quodeq evaluates real code and returns structured findings with severity, CWE classification, and file location:

```
CRITICAL  src/db.py:15        SQL Injection via string concatenation     CWE-89
          query = f"SELECT * FROM users WHERE id = {user_id}"

HIGH      src/auth.py:42      Hardcoded credentials in source code       CWE-798
          credentials = {"user": "admin", "pass": "secret123"}

MEDIUM    src/api.py:88       Missing rate limiting on login endpoint     CWE-307
          @app.route("/login", methods=["POST"])

MINOR     src/utils.py:23     Bare except clause hides errors             CWE-396
          except: pass
```

Each finding includes a reason, the offending snippet, and a fix plan. Results are stored as JSON on your machine and viewable in the dashboard or as raw files.

---

## Getting Started

```bash
pipx install quodeq    # Install quodeq
quodeq                 # Launch the dashboard
```

That's it. Running `quodeq` with no arguments opens the dashboard, where you can point to any project and run evaluations from the UI.

> Also available via `pip install quodeq`.

### Requirements

| Dependency | Version | |
|---|---|---|
| [Python](https://www.python.org/downloads/) | 3.12+ | Runtime (`brew install python` or [download](https://www.python.org/downloads/)) |
| [Node.js](https://nodejs.org/) | 18+ | Dashboard UI (`brew install node` or [download](https://nodejs.org/)) |

### AI Providers

Quodeq works with **local models** and **cloud AI CLIs**. Choose what fits your workflow.

#### Local models (free, private, your code never leaves your machine)

| Provider | Getting started |
|---|---|
| Ollama | [Installation guide](https://ollama.com/download) |

> We recommend [Gemma 4](https://deepmind.google/models/gemma/gemma-4/), specifically [`gemma4:26b`](https://ollama.com/library/gemma4:26b), for an excellent quality-to-cost ratio in local analysis. Reducing the context window to 32k still gives good results and allows running multiple subagents in parallel.

#### Cloud CLI providers (faster, deeper analysis)

| Provider | Getting started |
|---|---|
| Claude Code | [Installation guide](https://code.claude.com/docs/en/quickstart) |
| Codex CLI | [Installation guide](https://developers.openai.com/codex/quickstart) |
| Gemini CLI | [Installation guide](https://geminicli.com/docs/get-started/installation/) |

After installing a provider, go to **Settings** in the dashboard and select it.

> For cloud, Claude Sonnet gives the best balance of speed, quality, and cost.

---

## Dashboard

The Quodeq Dashboard is the main way to use Quodeq. Launch evaluations, browse results, and track quality over time.

```bash
quodeq                 # Launch the dashboard (default command)
quodeq dashboard       # Same as above, explicit form
```

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="res/dashboard-dark.png" />
    <img src="res/dashboard.png" alt="Quodeq Dashboard" width="900" />
  </picture>
</p>

Opens at `http://localhost:4173` with:

- **Overall grade and score** with A-F letter grade, numeric score /10, and trend across runs
- **Dimension breakdown** with individual scores per quality dimension and severity counts
- **Violations explorer** to drill into findings by file, principle, or CWE classification
- **Code map** showing a visual heatmap of your codebase and where issues concentrate
- **Top offending files** ranked by impact for focused remediation
- **Run history** to track how your codebase evolves over time
- **Custom standards** to create your own evaluation dimensions or import from the library

Click any dimension, file, or principle to explore the details. Dismiss false positives directly from the UI. Dismissed findings are excluded from future evaluations.

### CLI usage

You can also run evaluations directly from the terminal:

```bash
quodeq evaluate /path/to/project
quodeq evaluate /path/to/project --scope src/api    # Scoped to a subdirectory
quodeq evaluate /path/to/project -d security        # Single dimension
```

Run `quodeq evaluate --help` and `quodeq --help` for all available options.

---

## How It Works

1. **Detect** identifies the languages and structure of the codebase
2. **Analyze** sends an AI agent with read-only tools to explore the code
3. **Collect** findings stream as structured JSONL via tool calls
4. **Score** maps findings to ISO 25010 principles with CWE classifications
5. **Report** produces per-dimension reports with grades, violations, and compliance

Results are stored in `~/.quodeq/evaluations/` and persist across sessions.

## Standards

By default, Quodeq evaluates six quality dimensions based on **ISO 25010**: Security, Reliability, Maintainability, Performance, Flexibility, and Usability.

It also ships with additional built-in standards:

- **Clean Architecture** for layer separation, dependency rules, and boundary enforcement
- **Domain-Driven Design** for bounded contexts, aggregates, and ubiquitous language

You can **create your own standards** from the dashboard, or ask any AI to generate one as a `.json` file and import it. See the Help tab in the dashboard for the full schema.

## Supported Languages

Quodeq can evaluate **any codebase in any language**. The AI analysis engine reads and understands code regardless of the tech stack.

---

## Scoring

Quodeq scores each principle on a 0 to 10 scale using four independent constraints: violation base, compliance lift, violation ceiling, and severity grade floor. Full details in [the scoring formula documentation](src/quodeq/core/scoring/README.md).

## Development

```bash
git clone https://github.com/quodeq/quodeq.git && cd quodeq
uv sync
uv run pytest
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

## License

MIT. See [LICENSE](LICENSE).
