"""Constants shared across the llm_bridge package's own modules."""
from __future__ import annotations

# HTTP probe timeout for a local inference server's /health and model-list
# endpoints. Same value, same reason in all three backends (ollama,
# llama.cpp, omlx): these are localhost calls, so a short timeout still
# leaves room for a cold-started process without hanging the CLI.
TIMEOUT_S = 3
