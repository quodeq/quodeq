## AI Providers

Quodeq runs evaluations through one of three provider types. Pick what matches your privacy and cost constraints. You can switch any time from **Settings**.

### Cloud (OpenRouter or custom)

Routes through a hosted API using your key. Good when you want the latest frontier models without installing a CLI.

- **OpenRouter** single key, broad catalog. From cheapest to most capable, try `meta-llama/llama-3.1-8b-instruct:free`, `anthropic/claude-haiku-4-5`, `anthropic/claude-sonnet-4`, or `anthropic/claude-opus-4-7`.
- **Custom** any OpenAI-compatible endpoint. You provide the base URL and model id.

Use **Test connection** in the provider tab to verify the key and model before launching a real run.

### CLI (Claude Code, Codex, Gemini, GitHub Copilot)

Delegates to an AI CLI you already have authenticated on your machine. The CLI handles auth and billing; Quodeq drives it.

1. Install and sign in to your CLI of choice (Claude Code, Codex, Gemini CLI).
2. In **Settings → CLI Provider**, pick the binary and a model id like `gpt-5` or `claude-sonnet-4-6`.
3. Optionally pin a different model per power tier (Fast, Balanced, Thorough).

#### GitHub Copilot

Install GitHub Copilot CLI with `npm install -g @github/copilot`. Quodeq uses a
dedicated profile for evaluations and the embedded assistant. Sign in once with
your Copilot account:

```bash
COPILOT_HOME="$HOME/.quodeq/copilot" copilot login
```

In PowerShell, set `$env:COPILOT_HOME="$HOME/.quodeq/copilot"` before running
`copilot login`, then remove it with `Remove-Item Env:COPILOT_HOME`.

Select **GitHub Copilot** in Settings. The model dropdown loads the models
available to your signed-in account. Choose **Auto** or a specific model.
The evaluation, assistant, and tier-override selectors use the same account list.
Company policy, model access and usage limits still apply.
For Enterprise Cloud data residency, add `--host YOUR-ENTERPRISE.ghe.com` to login.
Repeat the same login command if authentication expires.

The setup message is hidden after a successful model lookup. If discovery fails,
the message and error are shown with **Retry connection**. No prompt is sent to
a model when loading this list.

The dedicated profile does not reuse your normal Copilot login, plugins or MCP
servers. Keep it for Quodeq only. Hooks, custom instructions and built-in MCP
servers are disabled. Evaluations can read source files and report findings;
the assistant uses only Quodeq's tools and existing write-grant controls.
Copilot does not support the assistant's web toggle.

### Ollama (local, private)

Runs entirely on your machine. Code never leaves the host. The trade-off is slower analysis and lower ceiling on quality compared to frontier cloud models.

1. Install Ollama from `ollama.com`.
2. Pull a capable instruction model, for example `ollama pull gemma4:26b`.
3. In **Settings → Ollama**, your installed models appear automatically. Pick one and set sub-agent count.

> **Picking sub-agent count**
>
> More sub-agents finish faster but use more tokens (cloud) or more VRAM (local). For local Ollama on a 32 GB machine, start with 2 or 3 and scale up only if you have headroom.

### omlx (Apple Silicon only)

On Apple Silicon Macs an extra local option appears: **Omlx**, an MLX-native server that runs models tuned for unified memory.

1. Start the server with `omlx serve` or the omlx menu bar app.
2. In **Settings → Omlx**, pick a model. The list comes from your local server; add models through the omlx admin UI at `http://localhost:8000/admin`.
3. Under *Advanced* you can set a custom server address, an API key, and run the parallel-agent auto-detect, which recommends a sub-agent count based on your unified memory.

### llama.cpp (local, GGUF models)

Points Quodeq at a llama-server instance you run yourself. It serves one GGUF model at a time, fixed at launch.

1. Start the server with `llama-server -m model.gguf --port 8080`.
2. In **Settings → llama.cpp**, the loaded model appears automatically. To switch models, restart llama-server with a different GGUF.
3. Under *Advanced*, run the parallel-agent auto-detect, which tests the server and recommends a sub-agent count.

### Power tiers

Each provider exposes three power levels that map to model size:

| Key | Value |
| --- | --- |
| Fast | Smallest tier. Good for routine runs and tight budgets. |
| Balanced | Default. Best quality-per-cost for most evaluations. |
| Thorough | Largest tier. Use for first scans, audits, or sensitive areas. |
