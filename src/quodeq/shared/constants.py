"""Cross-layer constants shared across bounded contexts."""

# Pool / subagent defaults
_DEFAULT_MAX_SUBAGENTS = 5
_DEFAULT_TIME_LIMIT = 600  # 10 minutes total time limit (seconds)
# Deprecated alias kept for any external import path; prefer _DEFAULT_TIME_LIMIT.
_DEFAULT_POOL_BUDGET = _DEFAULT_TIME_LIMIT

# Structured marker key used for job-tracking JSON markers
CC_MARKER_KEY = "_cc"
