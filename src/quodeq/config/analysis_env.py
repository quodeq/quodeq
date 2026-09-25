"""Environment-based configuration for the analysis pipeline.

``quodeq.analysis`` never reads the environment; overrides are resolved
here, lazily per call, and passed in.
"""
from __future__ import annotations

from collections.abc import Mapping

from quodeq.shared import env_int
from quodeq.shared.env_resolve import resolve_env
from quodeq.shared.csv_values import split_csv


def failure_streak_override(env: Mapping[str, str] | None = None) -> int | None:
    """Return the QUODEQ_FAILURE_STREAK override, or None when unset/malformed.

    The business rule (override wins over the configured
    ``failure_streak_threshold``, 0 disables the breaker, negative values
    clamp to 0) stays with the caller; this only resolves the raw override.
    """
    raw = resolve_env(env).get("QUODEQ_FAILURE_STREAK")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _digits_override(var: str, env: Mapping[str, str] | None) -> int | None:
    """*var* as a non-negative int when it is all digits (after trimming), else None."""
    raw = resolve_env(env).get(var, "").strip()
    return int(raw) if raw.isdigit() else None


def max_output_tokens_override(env: Mapping[str, str] | None = None) -> int | None:
    """Return the QUODEQ_MAX_OUTPUT_TOKENS override, or None when unset/malformed.

    The business rule (explicit config wins, cloud calls stay uncapped,
    0 disables the local cap) stays with the caller; this only resolves the
    raw override. Digit-parse only: negatives and blanks read as unset.
    """
    return _digits_override("QUODEQ_MAX_OUTPUT_TOKENS", env)


def api_read_timeout_override(env: Mapping[str, str] | None = None) -> int | None:
    """Return the QUODEQ_API_READ_TIMEOUT override (whole seconds), or None.

    The business rule (positive values override the read budget outright)
    stays with the caller; this only resolves the raw override. Digit-parse
    only: negatives and blanks read as unset.
    """
    return _digits_override("QUODEQ_API_READ_TIMEOUT", env)


def context_size_override(env: Mapping[str, str] | None = None) -> int | None:
    """Return the QUODEQ_CONTEXT_SIZE override, or None when unset/malformed.

    The business rule (env consulted only when the configured context size
    is unset, positive values forwarded as ``num_ctx``) stays with the
    caller; this only resolves the raw override.
    """
    return _digits_override("QUODEQ_CONTEXT_SIZE", env)


DEFAULT_MAX_TURNS_DEFAULT = 200
DEFAULT_MAX_DURATION_DEFAULT = 1800  # 30 minutes


def default_max_turns(env: Mapping[str, str] | None = None) -> int:
    """Turn ceiling per single-agent dimension, resolved once per run by the CLI."""
    return env_int("QUODEQ_DEFAULT_MAX_TURNS", DEFAULT_MAX_TURNS_DEFAULT, env=env)


def default_max_duration(env: Mapping[str, str] | None = None) -> int:
    """Wall-clock ceiling per single-agent dimension in seconds (30 min), resolved once per run."""
    return env_int("QUODEQ_DEFAULT_MAX_DURATION", DEFAULT_MAX_DURATION_DEFAULT, env=env)


_REPAIR_DISABLE_TRUTHY = frozenset({"1", "true", "yes", "on"})


def finding_repair_disabled(env: Mapping[str, str] | None = None) -> bool:
    """Return True when QUODEQ_DISABLE_FINDING_REPAIR is truthy.

    Operator kill switch for the snippet repair re-ask (one follow-up call
    asking the model to complete findings it emitted without the required
    verbatim ``snippet``). Off by default; set to disable the extra call for
    a model or provider where it misbehaves.
    """
    environ = resolve_env(env)
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
FAILURE_STREAK_THRESHOLD_DEFAULT = 5  # consecutive file_done errors that trip the dim breaker


def max_api_file_size(env: Mapping[str, str] | None = None) -> int:
    """Max file size (bytes, exclusive) an API provider will dispatch."""
    return env_int("QUODEQ_MAX_API_FILE_SIZE", MAX_API_FILE_SIZE_DEFAULT, env=env, warn=False)


def max_api_prompt_chars(env: Mapping[str, str] | None = None) -> int:
    """Max bytes of file content to inline per model call."""
    return env_int("QUODEQ_MAX_API_PROMPT_CHARS", MAX_API_PROMPT_CHARS_DEFAULT, env=env, warn=False)


def max_standards_chars(env: Mapping[str, str] | None = None) -> int:
    """Max chars of standards text to include in an API prompt."""
    return env_int("QUODEQ_MAX_STANDARDS_CHARS", MAX_STANDARDS_CHARS_DEFAULT, env=env, warn=False)


def mcp_max_batch(env: Mapping[str, str] | None = None) -> int:
    """Per-call file-batch ceiling for the findings MCP server.

    Unset, malformed and non-positive values all read as the default.
    """
    return env_int("QUODEQ_MCP_MAX_BATCH", MCP_MAX_BATCH_DEFAULT, minimum=1, env=env, warn=False)


def ai_tools(env: Mapping[str, str] | None = None) -> str:
    """Tool allow-list passed to the AI CLI (QUODEQ_AI_TOOLS)."""
    return resolve_env(env).get("QUODEQ_AI_TOOLS", AI_TOOLS_DEFAULT)


def base_ai_args(env: Mapping[str, str] | None = None) -> str:
    """Raw base args for the AI CLI (QUODEQ_AI_BASE_ARGS), unsplit."""
    return resolve_env(env).get(
        "QUODEQ_AI_BASE_ARGS", BASE_AI_ARGS_DEFAULT)


def non_scout_providers(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Providers that skip scout mode (no per-token billing)."""
    raw = resolve_env(env).get(
        "QUODEQ_NON_SCOUT_PROVIDERS", NON_SCOUT_PROVIDERS_DEFAULT)
    return tuple(split_csv(raw))


def subagent_model_override(env: Mapping[str, str] | None = None) -> str | None:
    """Subagent model override, or None to use the client's default.

    SUBAGENT_MODEL (set by the dashboard/service layer) wins over
    QUODEQ_SUBAGENT_MODEL (the direct operator override).
    """
    environ = resolve_env(env)
    return environ.get("SUBAGENT_MODEL") or environ.get("QUODEQ_SUBAGENT_MODEL") or None


def agent_failure_streak_limit(env: Mapping[str, str] | None = None) -> int:
    """Consecutive whole-agent failures tolerated before the run is cancelled.

    QUODEQ_AGENT_FAILURE_STREAK; 0 disables the backstop.
    """
    return env_int(
        "QUODEQ_AGENT_FAILURE_STREAK", AGENT_FAILURE_STREAK_DEFAULT, env=env, warn=False,
    )


def provider_explicitly_configured(env: Mapping[str, str] | None = None) -> bool:
    """True when the user has pinned a provider via AI_PROVIDER or AI_CMD."""
    environ = resolve_env(env)
    return "AI_PROVIDER" in environ or "AI_CMD" in environ
