"""What the pipeline does once, before the dimension loop starts.

Split from ``_pipeline.py`` to keep each module under 300 lines. Both names
are imported back there, so ``quodeq.analysis._pipeline.<name>`` stays the
place the loop looks them up.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from quodeq.analysis.provider_cache import get_provider_configs
from quodeq.analysis.run_types import RunConfig
from quodeq.analysis.runner_markers import emit_marker
from quodeq.analysis.subprocess import get_provider_type
from quodeq.config.provider import ProviderType
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.shared.constants import CC_PHASE_ANALYZING_START

_LOCAL_API_HOSTS = ("localhost", "127.0.0.1", "::1")


def warn_if_local_api_oversubscribed(
    config: RunConfig, *, log: LogSink = NULL_LOG,
) -> None:
    """Warn when subagents will queue behind one local-API inference slot.

    Local model servers (Ollama, llama.cpp, omlx) default to serving one
    request per loaded model, so with ``--n-subagents > 1`` the extra agents
    queue behind the first. The read timeout scales with the subagent count
    (see ``_api_call._resolve_timeout``) so queued calls no longer die, but
    throughput is still capped at the server's parallelism until it is raised
    (e.g. ``OLLAMA_NUM_PARALLEL``). Cloud API providers don't have this
    constraint, so we narrow the warning to loopback bases.
    """
    if config.options.max_subagents <= 1:
        return
    ai_cmd = config.ai_cmd
    if get_provider_type(ai_cmd) != ProviderType.API:
        return
    api_base = get_provider_configs().get(ai_cmd, {}).get("api_base", "")
    if not any(host in api_base for host in _LOCAL_API_HOSTS):
        return
    log.warning(
        f"--n-subagents={config.options.max_subagents} with local provider "
        f"'{ai_cmd}': local model servers serve one request per model by "
        f"default, so subagents queue and add little throughput. To run "
        f"them truly in parallel, raise the server's parallelism (e.g. "
        f"OLLAMA_NUM_PARALLEL={config.options.max_subagents})."
    )


def set_run_deadline(config: RunConfig) -> None:
    """Set the run-level deadline once, just before the dim loop starts.

    Skipped for dry runs (caller returns earlier), unlimited budget, or when
    an outer caller (tests) has pre-set deadline_at.
    """
    budget_s = config.options.time_limit
    if config.options.deadline_at is None and budget_s is not None and budget_s > 0:
        config.options.deadline_at = time.monotonic() + budget_s
        deadline_iso = (
            datetime.now(timezone.utc) + timedelta(seconds=budget_s)
        ).isoformat()
        emit_marker(CC_PHASE_ANALYZING_START, deadline_at=deadline_iso, budget_s=budget_s)
