<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="res/quodeq-logo-dark.svg" />
    <img src="res/quodeq-logo.svg" alt="Quodeq" width="340" />
  </picture>
</p>

<h2 align="center">AI-powered code quality and security scanner</h2>
<p align="center"><strong>v1.0.3</strong></p>
<p align="center">
  <a href="https://github.com/quodeq/quodeq/actions/workflows/test.yml"><img src="https://github.com/quodeq/quodeq/actions/workflows/test.yml/badge.svg" alt="Tests" /></a>
  <a href="https://github.com/quodeq/quodeq/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License" /></a>
  <a href="https://pypi.org/project/quodeq/"><img src="https://img.shields.io/pypi/v/quodeq.svg" alt="PyPI" /></a>
</p>

<p align="center">
  <a href="https://www.youtube.com/watch?v=C9feqpR5BMI&list=PLJjpl8sE7W-U1HMePWdGis7w834NPYD3R">Watch the 2-min demo</a> · <a href="https://quodeq.ai">Website</a> · <a href="https://quodeq.ai/blog/">Blog</a> · <a href="https://github.com/quodeq/quodeq/releases/latest">Releases</a>
</p>

---

AI models can now autonomously find and exploit zero-day vulnerabilities across operating systems, browsers, and web applications. Thousands of previously unknown flaws uncovered in weeks, not years.

The code you ship today will be read by models that can spot what humans miss. But the tools to prepare for this are locked behind enterprise contracts and partner programs.

Quodeq exists to change that.

**Open source. MIT license. Runs locally. No telemetry. No account. No servers.**

Scans any codebase with AI across six quality dimensions from [ISO 25010](https://www.iso.org/standard/35733.html):
**Security**, **Reliability**, **Maintainability**, **Performance**, **Flexibility**, and **Usability**.

Every finding maps to a [CWE](https://cwe.mitre.org/) identifier. You get grades, violations with line numbers, and a fix plan. Cloud providers (Claude, Gemini, Codex) for speed. Local models via [Ollama](https://ollama.com) for privacy.

---

## What It Finds

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

Each finding includes a reason, the offending code, and a fix plan. Results are stored as JSON on your machine.

---

## Getting Started

```bash
pipx install quodeq    # Install quodeq
quodeq                 # Launch the dashboard
```

Running `quodeq` opens the dashboard, where you can point to any project and run evaluations from the UI. Also available via `pip install quodeq`.

**Requirements:** [Python 3.12+](https://www.python.org/downloads/) and [Node.js 18+](https://nodejs.org/) (for the dashboard UI).

---

## Dashboard

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="res/dashboard-dark.png" />
    <img src="res/dashboard.png" alt="Quodeq Dashboard" width="900" />
  </picture>
</p>
<br>

- **Grades and scores** per dimension with A-F letter grades, numeric scores, and trends across runs
- **Violations explorer** to drill into findings by file, principle, or CWE classification
- **Code map** showing a visual heatmap of where issues concentrate in your codebase
- **Custom standards** to create your own evaluation dimensions or import from the library

Click any dimension, file, or principle to explore the details. Dismiss false positives directly from the UI.

Running `quodeq` is equivalent to `quodeq dashboard`. Both open the same UI.

### CLI

```bash
quodeq evaluate /path/to/project
quodeq evaluate /path/to/project --scope src/api    # Scoped to a subdirectory
quodeq evaluate /path/to/project -d security        # Single dimension
```

---

## AI Providers

Choose what fits your workflow. Configure in **Settings** from the dashboard.

| Provider | Type | Getting started |
|---|---|---|
| [Ollama](https://ollama.com/download) | Local | Free, private, code never leaves your machine |
| [Claude Code](https://code.claude.com/docs/en/quickstart) | Cloud | Best balance of speed, quality, and cost |
| [Codex CLI](https://developers.openai.com/codex/quickstart) | Cloud | OpenAI models |
| [Gemini CLI](https://geminicli.com/docs/get-started/installation/) | Cloud | Google models |

> For local analysis we recommend [Gemma 4](https://deepmind.google/models/gemma/gemma-4/) ([`gemma4:26b`](https://ollama.com/library/gemma4:26b)). Reducing the context window to 32k still gives good results and allows running multiple subagents in parallel.

---

## How It Works

1. **Detect** languages, frameworks, and project structure
2. **Analyze** with AI agents that read the code using read-only tools
3. **Collect** findings as structured JSONL via tool calls
4. **Score** against [ISO 25010](https://www.iso.org/standard/35733.html) principles with [CWE](https://cwe.mitre.org/) classifications
5. **Report** per-dimension grades, violations, compliance, and fix plans

Results are stored in `~/.quodeq/evaluations/` and persist across sessions. Works with any language. The AI analysis engine reads and understands code regardless of the tech stack.

Quodeq scores each principle on a 0 to 10 scale using four independent constraints. Full details in [the scoring formula documentation](src/quodeq/core/scoring/README.md).

### Standards

By default, Quodeq evaluates the six ISO 25010 dimensions. It also ships with **Clean Architecture** and **Domain-Driven Design** standards. You can create your own from the dashboard, or ask any AI to generate one as a `.json` file and import it.

---

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
