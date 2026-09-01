"""Subprocess environment building for evaluation runs.

Split (Task 14) out of ``evaluation_mixin.py``: ``build_eval_env`` is a free
function; ``FsEvaluationMixin._build_eval_env`` (kept in ``evaluation_mixin.py``
for its existing callers/tests) is a thin static-method delegate to it. The
``get_ai_cmd``/``get_ai_model`` fallback lookups stay in ``evaluation_mixin.py``
(patched there by tests), resolved before calling in here.
"""
from __future__ import annotations

import os

from quodeq.services.base import EvaluationOptions
from quodeq.shared.provider_env import provider_env_exports


def _apply_provider_credentials(built_env: dict[str, str], options: EvaluationOptions) -> None:
    """Export user-entered API credentials into *built_env* in place.

    Under the env names the scan subprocess resolves them from (provider's
    api_key_env). Without this, a key typed in Settings for e.g. OpenRouter
    never reached the run and it failed with a missing-key error.
    """
    built_env.update(provider_env_exports(
        options.ai_cmd, options.provider_api_key, options.provider_api_base,
    ))
    if options.ai_cmd == "omlx":
        if options.provider_api_key:
            built_env["OMLX_API_KEY"] = options.provider_api_key
        if options.provider_api_base:
            built_env["OMLX_BASE_URL"] = options.provider_api_base


def build_eval_env(
    repo: str, options: EvaluationOptions, env: dict[str, str] | None = None,
    *, ai_cmd: str, ai_model: str,
) -> dict[str, str]:
    """Build the subprocess environment for an evaluation run.

    *ai_cmd*/*ai_model* are the already-resolved values (``options.ai_cmd or
    get_ai_cmd()`` and its model equivalent) — resolved by the caller so the
    ``get_ai_cmd``/``get_ai_model`` lookups stay patchable at their existing
    call-site module (``evaluation_mixin``).
    """
    base = env if env is not None else os.environ
    built_env = {**base, "PYTHONUNBUFFERED": "1"}
    built_env["AI_CMD"] = ai_cmd
    # Validated at the API boundary (_validate_ai_cmd_path); the scan
    # subprocess spawns it as argv[0] while AI_CMD keeps keying the
    # provider config (analysis._command._cmd_binary).
    if options.ai_cmd_path:
        built_env["AI_CMD_PATH"] = options.ai_cmd_path
    subagent_model = options.subagent_model or ai_model
    # Ensure both env vars are set consistently — prevents model swapping
    # between verification (reads AI_MODEL) and analysis (reads SUBAGENT_MODEL)
    if ai_model:
        built_env["AI_MODEL"] = ai_model
    if subagent_model:
        built_env["SUBAGENT_MODEL"] = subagent_model
    if not options.verify_findings:
        built_env["QUODEQ_NO_VERIFY"] = "1"
    # Always propagate the limit, including 0 (unlimited). The CLI
    # subprocess uses positive values to set the run-level deadline
    # (lifecycle.set_deadline + analyzing_start marker) that the
    # dashboard's countdown depends on. An absent env var resolves to
    # None in the CLI and the pool substitutes its 600s default, so
    # skipping 0 turned "unlimited" into a 10-minute run.
    if options.time_limit is not None and options.time_limit >= 0:
        built_env["QUODEQ_TIME_LIMIT"] = str(options.time_limit)
    if options.per_dimension:
        built_env["QUODEQ_NO_CONSOLIDATE"] = "1"
    if options.context_size > 0:
        built_env["QUODEQ_CONTEXT_SIZE"] = str(options.context_size)
    _apply_provider_credentials(built_env, options)
    return built_env
