"""Core-wide constants. ``core`` may not import ``shared``, and this leaf imports nothing."""
# House-standard, and it also keeps this import-less module indexed by
# core/checks/framework_deps (edge-keyed; see the follow-up on ImportGraph.files).
from __future__ import annotations

FULL_CONFIDENCE = 100  # a finding the scanner is fully sure of; downweights subtract from this

# Python's package-marker module stem; not a segment of the dotted package
# name. Read by core/checks/framework_deps.py and data/fs/import_graph.py.
INIT_STEM = "__init__"

# sys.platform value. Lives here (not shared/constants.py) because core may
# not import shared; shared/constants.py re-exports it for everyone else.
PLATFORM_WIN32 = "win32"

# Per-provider MCP wiring styles, keyed by the "mcp_style" field of the
# ai_providers.json catalog. Read by both analysis/ (dimension-analysis
# subprocess dispatch: _mcp_arg_builders.py, subprocess.py) and assistant/
# (interactive CLI chat: adapters/_cli*.py, orchestrator.py) -- both load the
# same catalog (quodeq.assistant.get_provider_configs), so the value space
# and its default are shared here rather than re-typed per consumer.
MCP_STYLE_CONFIG_FILE = "config-file"  # --mcp-config <path>; the default when unset
MCP_STYLE_CONFIG_ARG = "config-arg"  # inline -c mcp_servers.<name>... args (codex)
MCP_STYLE_CLI_REGISTER = "cli-register"  # `<cmd> mcp add` out-of-band registration (gemini)

# The argv flag MCP_STYLE_CONFIG_ARG emits the inline config under. Both
# emitters (analysis/_mcp_arg_builders.py for the analysis subprocess,
# assistant/adapters/_cli_command.py for a chat turn) build argv for the same
# codex CLI, so the spelling lives next to the style it belongs to rather than
# being retyped on each side. Not a prompt flag: see PROMPT_FLAG_DEFAULT.
MCP_CONFIG_ARG_FLAG = "-c"

# Same catalog, same cross-feature readers as the MCP_STYLE_* trio above.
PROMPT_STYLE_FLAG = "flag"  # prompt passed via prompt_flag (e.g. -p); the default when unset
PROMPT_STYLE_POSITIONAL = "positional"  # prompt passed as a trailing positional arg
PROMPT_FLAG_DEFAULT = "-p"  # prompt_flag's own default when the provider config omits it
