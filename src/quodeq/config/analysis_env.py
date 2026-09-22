"""Environment-based configuration for the analysis pipeline.

``quodeq.analysis`` never reads the environment; overrides are resolved
here, lazily per call, and passed in.
"""
from __future__ import annotations

import os
from collections.abc import Mapping

from quodeq.shared import env_int


def failure_streak_override(env: dict[str, str] | None = None) -> int | None:
    """Return the QUODEQ_FAILURE_STREAK override, or None when unset/malformed.

    The business rule (override wins over the configured
    ``failure_streak_threshold``, 0 disables the breaker, negative values
    clamp to 0) stays with the caller; this only resolves the raw override.
    """
    raw = (os.environ if env is None else env).get("QUODEQ_FAILURE_STREAK")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def max_output_tokens_override(env: dict[str, str] | None = None) -> int | None:
    """Return the QUODEQ_MAX_OUTPUT_TOKENS override, or None when unset/malformed.

    The business rule (explicit config wins, cloud calls stay uncapped,
    0 disables the local cap) stays with the caller; this only resolves the
    raw override. Digit-parse only: negatives and blanks read as unset.
    """
    raw = (os.environ if env is None else env).get("QUODEQ_MAX_OUTPUT_TOKENS", "").strip()
    return int(raw) if raw.isdigit() else None


def api_read_timeout_override(env: dict[str, str] | None = None) -> int | None:
    """Return the QUODEQ_API_READ_TIMEOUT override (whole seconds), or None.

    The business rule (positive values override the read budget outright)
    stays with the caller; this only resolves the raw override. Digit-parse
    only: negatives and blanks read as unset.
    """
    raw = (os.environ if env is None else env).get("QUODEQ_API_READ_TIMEOUT", "").strip()
    return int(raw) if raw.isdigit() else None


def context_size_override(env: dict[str, str] | None = None) -> int | None:
    """Return the QUODEQ_CONTEXT_SIZE override, or None when unset/malformed.

    The business rule (env consulted only when the configured context size
    is unset, positive values forwarded as ``num_ctx``) stays with the
    caller; this only resolves the raw override.
    """
    raw = (os.environ if env is None else env).get("QUODEQ_CONTEXT_SIZE", "").strip()
    return int(raw) if raw.isdigit() else None


_DEFAULT_MAX_TURNS = 200
_DEFAULT_MAX_DURATION_S = 1800  # 30 minutes


def default_max_turns(env: dict[str, str] | None = None) -> int:
    """Turn ceiling per agent, resolved per construction (not at import)."""
    return env_int("QUODEQ_DEFAULT_MAX_TURNS", _DEFAULT_MAX_TURNS, env=env)


def default_max_duration(env: dict[str, str] | None = None) -> int:
    """Wall-clock ceiling per agent in seconds (30 min), resolved per construction."""
    return env_int("QUODEQ_DEFAULT_MAX_DURATION", _DEFAULT_MAX_DURATION_S, env=env)


_REPAIR_DISABLE_TRUTHY = frozenset({"1", "true", "yes", "on"})


def finding_repair_disabled(env: dict[str, str] | None = None) -> bool:
    """Return True when QUODEQ_DISABLE_FINDING_REPAIR is truthy.

    Operator kill switch for the snippet repair re-ask (one follow-up call
    asking the model to complete findings it emitted without the required
    verbatim ``snippet``). Off by default; set to disable the extra call for
    a model or provider where it misbehaves.
    """
    environ = env if env is not None else os.environ
    raw = environ.get("QUODEQ_DISABLE_FINDING_REPAIR", "")
    return raw.strip().lower() in _REPAIR_DISABLE_TRUTHY


# --- Prompt / dispatch caps -------------------------------------------------
#
# The three caps below share one shape: unset (or empty) means the packaged
# default, a malformed value falls back to it rather than raising.

MAX_API_FILE_SIZE_DEFAULT = 15000
MAX_API_PROMPT_CHARS_DEFAULT = 30000  # inlined-file budget for local models (~8K tokens)
MAX_STANDARDS_CHARS_DEFAULT = 50000  # full standards for models with large context
MCP_MAX_BATCH_DEFAULT = 1000
AI_TOOLS_DEFAULT = "Glob,Grep,Read"
BASE_AI_ARGS_DEFAULT = "--print --output-format stream-json --verbose"
NON_SCOUT_PROVIDERS_DEFAULT = "codex,gemini"
AGENT_FAILURE_STREAK_DEFAULT = 5


def _capped_int(environ: Mapping[str, str], var: str, default: int) -> int:
    """Read *var* as an int; empty or malformed reads as *default*."""
    raw = environ.get(var, "")
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def max_api_file_size(env: Mapping[str, str] | None = None) -> int:
    """Max file size (bytes, exclusive) an API provider will dispatch."""
    return _capped_int(
        os.environ if env is None else env,
        "QUODEQ_MAX_API_FILE_SIZE",
        MAX_API_FILE_SIZE_DEFAULT,
    )


def max_api_prompt_chars(env: Mapping[str, str] | None = None) -> int:
    """Max bytes of file content to inline per model call."""
    return _capped_int(
        os.environ if env is None else env,
        "QUODEQ_MAX_API_PROMPT_CHARS",
        MAX_API_PROMPT_CHARS_DEFAULT,
    )


def max_standards_chars(env: Mapping[str, str] | None = None) -> int:
    """Max chars of standards text to include in an API prompt."""
    return _capped_int(
        os.environ if env is None else env,
        "QUODEQ_MAX_STANDARDS_CHARS",
        MAX_STANDARDS_CHARS_DEFAULT,
    )


def mcp_max_batch(env: Mapping[str, str] | None = None) -> int:
    """Per-call file-batch ceiling for the findings MCP server.

    Unset, malformed and non-positive values all read as the default.
    """
    raw = (os.environ if env is None else env).get("QUODEQ_MCP_MAX_BATCH")
    if not raw:
        return MCP_MAX_BATCH_DEFAULT
    try:
        value = int(raw)
    except ValueError:
        return MCP_MAX_BATCH_DEFAULT
    return value if value > 0 else MCP_MAX_BATCH_DEFAULT


def ai_tools(env: Mapping[str, str] | None = None) -> str:
    """Tool allow-list passed to the AI CLI (QUODEQ_AI_TOOLS)."""
    return (os.environ if env is None else env).get("QUODEQ_AI_TOOLS", AI_TOOLS_DEFAULT)


def base_ai_args(env: Mapping[str, str] | None = None) -> str:
    """Raw base args for the AI CLI (QUODEQ_AI_BASE_ARGS), unsplit."""
    return (os.environ if env is None else env).get(
        "QUODEQ_AI_BASE_ARGS", BASE_AI_ARGS_DEFAULT)


def non_scout_providers(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Providers that skip scout mode (no per-token billing)."""
    raw = (os.environ if env is None else env).get(
        "QUODEQ_NON_SCOUT_PROVIDERS", NON_SCOUT_PROVIDERS_DEFAULT)
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def subagent_model_override(env: Mapping[str, str] | None = None) -> str | None:
    """Subagent model override, or None to use the client's default.

    SUBAGENT_MODEL (set by the dashboard/service layer) wins over
    QUODEQ_SUBAGENT_MODEL (the direct operator override).
    """
    environ = os.environ if env is None else env
    return environ.get("SUBAGENT_MODEL") or environ.get("QUODEQ_SUBAGENT_MODEL") or None


def agent_failure_streak_limit(env: Mapping[str, str] | None = None) -> int:
    """Consecutive whole-agent failures tolerated before the run is cancelled.

    QUODEQ_AGENT_FAILURE_STREAK; 0 disables the backstop.
    """
    raw = (os.environ if env is None else env).get(
        "QUODEQ_AGENT_FAILURE_STREAK", "").strip()
    try:
        return int(raw) if raw else AGENT_FAILURE_STREAK_DEFAULT
    except ValueError:
        return AGENT_FAILURE_STREAK_DEFAULT


def provider_explicitly_configured(env: Mapping[str, str] | None = None) -> bool:
    """True when the user has pinned a provider via AI_PROVIDER or AI_CMD."""
    environ = os.environ if env is None else env
    return "AI_PROVIDER" in environ or "AI_CMD" in environ
