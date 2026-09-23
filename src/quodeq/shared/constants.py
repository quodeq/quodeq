"""Cross-layer constants shared across bounded contexts."""
# House-standard, and it also keeps this import-less module indexed by
# core/checks/framework_deps (edge-keyed; see the follow-up on ImportGraph.files).
from __future__ import annotations

# Pool / subagent defaults
DEFAULT_MAX_SUBAGENTS = 5
DEFAULT_TIME_LIMIT = 600  # 10 minutes total time limit (seconds)

# Structured marker key used for job-tracking JSON markers
CC_MARKER_KEY = "_cc"

# CC_MARKER_KEY's value vocabulary. Written by analysis/runner_markers.py's
# emit_marker (and callers across analysis/), read back by
# services/_job_monitor_mixin.py's _apply_marker; both layers import from here
# since services may not import analysis.
CC_PHASE_SETUP = "setup"
CC_PHASE_ANALYZING = "analyzing"
CC_PHASE_SCORING = "scoring"
CC_PHASE_ANALYZING_START = "analyzing_start"
CC_PHASE_DEADLINE_EXTENDED = "deadline_extended"
CC_PHASE_REPORT_PATH = "report_path"

# Ollama's default listening port and the base URL local providers fall back to.
OLLAMA_DEFAULT_PORT = "11434"
OLLAMA_DEFAULT_BASE_URL = f"http://localhost:{OLLAMA_DEFAULT_PORT}"

# llama-server's default listening address, used when LLAMACPP_BASE_URL is unset.
DEFAULT_LLAMACPP_BASE_URL = "http://localhost:8080"

# omlx's default listening address, used when OMLX_BASE_URL is unset.
OMLX_DEFAULT_BASE_URL = "http://localhost:8000"

SECRET_SUFFIX_CHARS = 4  # how many trailing credential characters a log or settings mask may show
