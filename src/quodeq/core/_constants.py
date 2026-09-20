"""Core-wide constants. ``core`` may not import ``shared``, and this leaf imports nothing."""
# House-standard, and it also keeps this import-less module indexed by
# core/checks/framework_deps (edge-keyed; see the follow-up on ImportGraph.files).
from __future__ import annotations

FULL_CONFIDENCE = 100  # a finding the scanner is fully sure of; downweights subtract from this

# Per-provider MCP wiring styles, keyed by the "mcp_style" field of the
# ai_providers.json catalog. Read by both analysis/ (dimension-analysis
# subprocess dispatch: _mcp_arg_builders.py, subprocess.py) and assistant/
# (interactive CLI chat: adapters/_cli*.py, orchestrator.py) -- both load the
# same catalog (quodeq.assistant.get_provider_configs), so the value space
# and its default are shared here rather than re-typed per consumer.
MCP_STYLE_CONFIG_FILE = "config-file"  # --mcp-config <path>; the default when unset
MCP_STYLE_CONFIG_ARG = "config-arg"  # inline -c mcp_servers.<name>... args (codex)
MCP_STYLE_CLI_REGISTER = "cli-register"  # `<cmd> mcp add` out-of-band registration (gemini)

# Same catalog, same cross-feature readers as the MCP_STYLE_* trio above.
PROMPT_STYLE_FLAG = "flag"  # prompt passed via prompt_flag (e.g. -p); the default when unset
PROMPT_STYLE_POSITIONAL = "positional"  # prompt passed as a trailing positional arg
PROMPT_FLAG_DEFAULT = "-p"  # prompt_flag's own default when the provider config omits it
