## Command Line

The dashboard is one subcommand of the `quodeq` CLI. The rest run headless: scripted evaluations, pull-request reviews, and machine-readable exports.

### Commands

| Key | Value |
| --- | --- |
| quodeq | Launch the dashboard. Same as `quodeq dashboard`. If one is already running, it focuses the existing window instead of starting a second server. Once the window is open the terminal is yours again; `--foreground` keeps it attached. `--browser` opens it in your browser instead of the window. Typing the address by hand does not open the app: the local server only answers the window or browser tab quodeq opened. |
| quodeq status | Show whether the window and its API are running, and which evaluations are in progress. It exits with 0 while the window or its API runs and with 3 when neither does, so a script can test it. |
| quodeq stop | Close the window and stop its API, also when the window no longer responds. Running evaluations keep going. |
| quodeq restart | Stop the window and its API, then open Quodeq again. Running evaluations keep going. The Restart now button after an in-app upgrade runs this. |
| quodeq upgrade | Upgrade quodeq with the tool you installed it with: pipx, uv, Homebrew, or the pip of the Python it runs from. `--dry-run` prints the command without running it. The desktop app updates from its own download instead. |
| quodeq evaluate &lt;repo&gt; | Run an evaluation without the UI. Takes a path or URL. |
| quodeq review | Evaluate your current branch and post the findings as a GitHub pull request review. |
| quodeq export sarif | Convert a finished evaluation to a SARIF file. |
| quodeq ci report | Post evaluation results on a GitHub pull request from inside a CI pipeline. |

### Evaluate flags worth knowing

- `--dimensions` a comma-separated subset instead of all dimensions.
- `--branch` and `--scope` analyze a branch (via a temporary worktree) or a subdirectory.
- `--time-limit` total seconds for the run; 0 means unlimited. quodeq scores whatever finished in time.
- `--clean-scan` ignore cached findings and re-analyze every file.
- `--evidence-only` collect findings but skip scoring.
- `--diff-from <ref>` analyze only the files changed since a git ref. Evidence only, no scores: grading part of a codebase would mislead.
- `--output <dir>` write the run somewhere other than `~/.quodeq/evaluations`.

### Without the dashboard

A headless run takes its provider and model from the environment when they are set there, otherwise from what Settings saved.

| Key | Value |
| --- | --- |
| AI_PROVIDER | One of `claude`, `codex`, `gemini`, `agy`, `copilot`, `openrouter`, `custom`, `ollama`, `llamacpp`. |
| AI_MODEL | The model id for that provider. `QUODEQ_MODEL_LIGHT`, `QUODEQ_MODEL_MEDIUM`, `QUODEQ_MODEL_HIGH` and `QUODEQ_MODEL_ORCHESTRATOR` pin a model per tier and take precedence. |
| AI_EFFORT | Reasoning effort for Claude Code (`low`, `medium`, `high`, `xhigh`, `max`) Codex (`low`, `medium`, `high`, `xhigh`, `max`, `ultra`; which ones a model takes depends on the model) or Antigravity (`low`, `medium`, `high`, `xhigh`, `max`). Unset leaves the CLI default. |
| API keys | `ANTHROPIC_API_KEY`, `CODEX_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, or `AI_API_KEY` for a custom endpoint. The CLI providers use the CLI's own sign-in; Ollama and llama.cpp need no key. |
| QUODEQ_REPOS_DIR | Where clones of remote repositories go. Default `~/quodeq/repos`. |
| QUODEQ_REQUIRE_SANDBOX | Set to `1` to make a scan fail when its AI CLI cannot be put in a sandbox, instead of running without one. See *How the CLI is confined* in *AI Providers*. |
| QUODEQ_NO_UPDATE_NOTIFIER | Set to `1` to silence the update check. It is already silent when `CI` is set. |

### In CI

Reviewing pull requests, running in a pipeline and exporting SARIF for code scanning are described together in *Connect to CI*.

> **Every command documents itself**
>
> `quodeq <command> --help` prints the full flag list, including defaults.
