"""Cross-layer constants shared across bounded contexts."""
# House-standard, and it also keeps this import-less module indexed by
# core/checks/framework_deps (edge-keyed; see the follow-up on ImportGraph.files).
from __future__ import annotations

# Pool / subagent defaults
DEFAULT_MAX_SUBAGENTS = 5
DEFAULT_TIME_LIMIT = 600  # 10 minutes total time limit (seconds)

# Structured marker key used for job-tracking JSON markers
CC_MARKER_KEY = "_cc"

# Assistant-session source: the user's own repo ("local") vs a read-only
# shared-results mirror ("shared"). Not the project location, which uses
# "local"/"online" on a different axis.
SESSION_SOURCE_LOCAL = "local"
SESSION_SOURCE_SHARED = "shared"
SESSION_SOURCES = (SESSION_SOURCE_LOCAL, SESSION_SOURCE_SHARED)

# Ollama's default listening port and the base URL local providers fall back to.
OLLAMA_DEFAULT_PORT = "11434"
OLLAMA_DEFAULT_BASE_URL = f"http://localhost:{OLLAMA_DEFAULT_PORT}"

# llama-server's default listening address, used when LLAMACPP_BASE_URL is unset.
DEFAULT_LLAMACPP_BASE_URL = "http://localhost:8080"

# omlx's default listening address, used when OMLX_BASE_URL is unset.
OMLX_DEFAULT_BASE_URL = "http://localhost:8000"

SECRET_SUFFIX_CHARS = 4  # how many trailing credential characters a log or settings mask may show
