<p align="center">
  <img src="res/quodeq-logo.svg#gh-light-mode-only" alt="Quodeq" width="340" />
  <img src="res/quodeq-logo-dark.svg#gh-dark-mode-only" alt="Quodeq" width="340" />
</p>

<h2 align="center">AI-powered code quality and security scanner</h2>
<p align="center">
  <a href="https://github.com/quodeq/quodeq/actions/workflows/test.yml"><img src="https://github.com/quodeq/quodeq/actions/workflows/test.yml/badge.svg" alt="Tests" /></a>
  <a href="https://github.com/quodeq/quodeq/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License" /></a>
  <a href="https://pypi.org/project/quodeq/"><img src="https://img.shields.io/pypi/v/quodeq.svg" alt="PyPI" /></a>
</p>

<p align="center">
  <a href="https://quodeq.ai">Website</a> · <a href="https://quodeq.ai/docs/">Docs</a> · <a href="https://www.youtube.com/watch?v=Ie7rAiPBDQE&list=PLJjpl8sE7W-U1HMePWdGis7w834NPYD3R&index=1">Demo</a> · <a href="https://quodeq.ai/blog/">Blog</a> · <a href="https://github.com/quodeq/quodeq/discussions">Discussions</a> · <a href="https://github.com/quodeq/quodeq/releases/latest">Releases</a>
</p>

---

Quodeq reviews a codebase with the AI model you choose, against standards you can read and change: the six quality dimensions of [ISO 25010](https://www.iso.org/standard/35733.html) out of the box, and your team's own rules next to them. Every finding names the rule it breaks, the file and line, and the reason, so the last word stays with you. It is open source under the MIT license and runs on your machine, with no account, no Quodeq server and no telemetry.

<p align="center">
  <img src="res/dashboard.png#gh-light-mode-only" alt="The Quodeq Overview: the project's grade, each dimension's score and trend, the score history and what to fix first" width="900" />
  <img src="res/dashboard-dark.png#gh-dark-mode-only" alt="The Quodeq Overview: the project's grade, each dimension's score and trend, the score history and what to fix first" width="900" />
</p>
<p align="center"><sub>The Overview of a project: the grade, the dimensions, the score history, what to fix first.</sub></p>

## What it finds

```
CRITICAL    src/db.py:15        SQL injection via string concatenation     CWE-89
            query = f"SELECT * FROM users WHERE id = {user_id}"

MAJOR       src/auth.py:42      Hardcoded credentials in source code       CWE-798
            credentials = {"user": "admin", "pass": "secret123"}

MINOR       src/utils.py:23     Bare except clause hides errors            CWE-396
            except: pass

COMPLIANT   src/api.py:88       Parameterized query prevents injection     CWE-89
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```

Each finding comes with its reason, the code and a fix plan, and code done right is counted too, so a grade reflects both sides. Security, reliability, maintainability, performance, flexibility and usability are each graded from 0 to 10, and the dashboard shows where the issues sit in a code map, how they change from run to run, and how your projects compare.

## Get started

1. **Install it.** With Python 3.12 or newer, `pipx install quodeq`, or on macOS `brew install quodeq/tap/quodeq`.
2. **Have a model at hand.** quodeq works with an AI CLI you already use (Claude Code, Codex, Gemini CLI, Antigravity, GitHub Copilot), an OpenRouter key, or a local model through Ollama, llama.cpp or omlx, in which case the code never leaves your machine. The [benchmarks](https://quodeq.ai/benchmarks/) show how models compare on a known corpus, and the [providers page](https://quodeq.ai/docs/providers/) has the setup for each.
3. **Run `quodeq`**, the same as `quodeq dashboard`. The dashboard opens with a welcome: add a repository, pick who reviews it, and start the first evaluation. Where the native window is not available (Linux without GTK and WebKit, Windows with an ARM64 Python), quodeq opens in your browser; `quodeq --browser` asks for that on any platform.

The [quickstart](https://quodeq.ai/docs/quickstart/) walks through the same steps in more detail.

## Your own standards

A standard is a set of principles and requirements, and one you add is graded exactly like a built-in one, with its own place in the Overview, the code map and Compare. Write it in the dashboard, import a file, or ask the assistant to draft one from a source you name, such as a style guide or your framework's documentation; nothing is created until you press Apply. Clean Architecture, Domain-Driven Design, Accessibility and AI Integration Security ship ready to switch on. See [Custom Standards](https://quodeq.ai/docs/standards/).

## Go further

- [Pull requests and CI](https://quodeq.ai/docs/cli/): review a pull request, post findings from a pipeline, and upload SARIF to code scanning.
- [AI providers](https://quodeq.ai/docs/providers/): every provider, including GitHub Copilot's own login and llama.cpp.
- [Running evaluations](https://quodeq.ai/docs/evaluations/): incremental and clean scans, time limits, and keeping paths out with `.quodeqignore`.
- [Violations and fix plans](https://quodeq.ai/docs/violations/): the findings workbench, dismissing a false positive, and declaring your project's threat model.
- [Why this grade](https://quodeq.ai/docs/why-this-grade/): how findings become scores, and the [scoring formula](src/quodeq/core/scoring/README.md) in full.
- [Command line](https://quodeq.ai/docs/cli/): every command and the flags worth knowing.
- [Privacy](https://quodeq.ai/docs/privacy/): what stays on your machine, and the daily update check, the only request quodeq makes on its own.
- [Desktop builds (beta)](https://github.com/quodeq/quodeq/releases/latest): unsigned macOS and Windows apps attached to each release.

## Development

```bash
git clone https://github.com/quodeq/quodeq.git && cd quodeq
uv sync                   # install Python deps into .venv/
uv run quodeq             # launch the dashboard
uv run pytest             # run the test suite
```

A source checkout builds the dashboard UI from the working copy, so it needs Node 20+ and npm 10+ besides Python 3.12+. [CONTRIBUTING.md](CONTRIBUTING.md) covers the setup, the test suite and how changes get reviewed.

## Contributing

Issues and pull requests are welcome, and everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

- **Found a bug or want a feature?** [Open an issue](https://github.com/quodeq/quodeq/issues).
- **Want to ask something, or show what you built?** [Discussions](https://github.com/quodeq/quodeq/discussions).
- **Found a security problem?** Please don't open a public issue. [SECURITY.md](SECURITY.md) has the disclosure process.

Release history is in [CHANGELOG.md](CHANGELOG.md), and the readable version in the [release announcements](https://github.com/quodeq/quodeq/discussions/categories/announcements). If Quodeq is useful to you, starring the repo helps other people find it.

## License

MIT. See [LICENSE](LICENSE).
