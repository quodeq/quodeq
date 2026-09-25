"""Cross-layer constants shared across bounded contexts."""
from __future__ import annotations

# core may not import shared, but shared may import core -- re-exported here
# so callers outside core keep one import path for every PLATFORM_* name.
from quodeq.core.constants import PLATFORM_WIN32  # noqa: F401

# sys.platform values for cross-platform branches.
PLATFORM_DARWIN = "darwin"

# platform.system() values -- a different vocabulary from sys.platform
# ("Darwin"/"Linux" vs "darwin"/"win32").
SYSTEM_DARWIN = "Darwin"
SYSTEM_LINUX = "Linux"
MACHINE_ARM64 = "arm64"  # platform.machine() on Apple silicon (Homebrew prefix, native tooling picks)

# URL schemes the app's fetchers and SSRF guards allow.
SCHEME_HTTP = "http"
SCHEME_HTTPS = "https"

# Loopback hostnames blocked/allowed by SSRF and authority checks.
LOCALHOST = "localhost"
LOCALHOST_LOCALDOMAIN = "localhost.localdomain"  # glibc's alternate loopback hostname

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

# Time unit conversion. Read by analysis/runner_markers.py and
# analysis/subagents/_heartbeat.py to render elapsed seconds as mm:ss.
SECONDS_PER_MINUTE = 60

# Exponential-backoff retry formula shared by two independent network
# retry loops (config/_asvs_network.py's ASVS fetch, update/download.py's
# release download): base_delay * 2**attempt + uniform(0, jitter).
RETRY_BASE_DELAY_S = 0.5
RETRY_JITTER_S = 0.3

# Bound on a `which`/shell-discovery subprocess probe. Shared by
# shared/frozen.py's PATH discovery and menubar/_health.py's per-command
# `which` probe; both are local subprocess calls, so a short timeout still
# leaves headroom for a slow shell init.
CMD_DISCOVERY_TIMEOUT_S = 5

# Per-run subdirectory holding evidence/*.jsonl, manifest.json and the live
# stream files. Named by analysis/data/services alike (analysis writes it,
# data and services read it), so it lives here rather than in one layer.
EVIDENCE_DIRNAME = "evidence"

# The run's evidence manifest (evidence/manifest.json) and the project-export
# zip's top-level manifest share this filename. Written by the CLI pipeline,
# read by data/services, copied by publish staging and zipped by api/zip.py.
MANIFEST_FILENAME = "manifest.json"

# git argv pieces and the repo metadata directory, used by the CLI worktree
# helpers, assistant/worktree.py, data/git_cli.py and the shared-repo cache.
GIT_BIN = "git"  # argv[0] for a git subprocess
GIT_FLAG_C = "-C"  # git's global "run as if started in <path>" flag
GIT_DIR_NAME = ".git"  # a checkout's metadata directory (also a path segment the assistant jail refuses)

ENV_TRUTHY = "1"  # the spelling quodeq's on/off env flags use (QUODEQ_VERBOSE, QUODEQ_NO_VERIFY, ...)

# Synthetic dimension id for a consolidated run (multiple dimensions handled
# by one agent pool/prompt instead of one pool per dimension). Used as the
# evidence-file prefix and progress-tracking id by analysis/subagents/pool.py
# and read back by services/_scan_progress_dims.py.
CONSOLIDATED_DIMENSION_KEY = "consolidated"

# Suffix of a run's per-dimension scored report files under its evaluation/
# directory. Checked by data/fs/report_parser and services/scoring alike.
JSON_SUFFIX = ".json"
