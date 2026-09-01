"""AI analysis runner -- dispatches to CLI subprocess or API runner.

This module is the public entry point. Implementation is split across:
- _config.py:               AnalysisConfig, HeartbeatCallback, dataclasses
- _mcp_config.py:            MCP config file creation
- _command.py:               CLI argument and environment construction
- _mcp_arg_builders.py:      MCP/tool/model arg construction for _command.py
- _process.py:               Process spawning, heartbeat, error handling
- _api_runner.py:            OpenAI SDK-based direct API runner
- _api_standards_text.py:    Source-file gathering + compiled standards text
                              for the API prompt
- _api_source_gathering.py:  Credential loaders + queue-aware file batching
                              for the API runner
"""
from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path

from quodeq.analysis._api_source_gathering import (
    _batch_files_by_size,
    _CREDENTIAL_LOADERS,
    _gather_api_source_files,
)
from quodeq.analysis._api_standards_text import (
    _api_prompt_char_budget,
    _gather_source_files,  # noqa: F401 -- re-export
    _load_standards_text,
    _render_standards_grouped,  # noqa: F401 -- re-export
    _SKIP_DIRS,  # noqa: F401 -- re-export
)
from quodeq.analysis._command import (
    _build_ai_cmd,
    _build_analysis_env,
    _register_cli_mcp,
    _unregister_cli_mcp,
)
from quodeq.analysis._config import AnalysisConfig, HeartbeatCallback, _SpawnPaths
from quodeq.analysis._process import AnalysisError, _check_process_result, _spawn_and_monitor
from quodeq.analysis._provider_cache import get_provider_configs
from quodeq.analysis.api_prompt_assembly import assemble_api_prompt
from quodeq.analysis.stream.counters import count_files_in_stream
from quodeq.context.trust_model import TrustModel, resolve_trust_model
from quodeq.shared import cancellation
from quodeq.shared.utils import get_ai_cmd


def _safe_int(value: str, default: int = 0) -> int:
    """Convert string to int, returning *default* on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

_log = logging.getLogger(__name__)

# Re-export public API so existing imports keep working
__all__ = [
    "AnalysisConfig",
    "AnalysisError",
    "HeartbeatCallback",
    "count_files_from_stream",
    "run_analysis",
    "_build_ai_cmd",
]


def count_files_from_stream(stream_file: Path) -> int:
    """Public: count unique files read by the AI from the stream file."""
    return len(count_files_in_stream(stream_file))


def _get_provider_type(ai_cmd: str) -> str:
    """Determine the provider type (cli or api) from the provider config."""
    configs = get_provider_configs()
    provider_cfg = configs.get(ai_cmd, {})
    return provider_cfg.get("type", "cli")


def _run_cli_analysis(
    work_dir: Path, prompt: str, stream_file: Path, cfg: AnalysisConfig,
) -> None:
    """Run analysis via CLI subprocess."""
    ai_cmd = cfg.ai_cmd or get_ai_cmd()
    # ai_cmd comes from the AI_CMD/AI_PROVIDER env var and is gated to known
    # providers in _register_cli_mcp before any subprocess call; it runs via a
    # subprocess list (no shell injection). Skipping shutil.which for CI/PATH.
    configs = get_provider_configs()
    provider_cfg = configs.get(ai_cmd, {})
    mcp_style = provider_cfg.get("mcp_style", "config-file")

    # For cli-register providers (e.g. Gemini), register MCP server before the run.
    # Registration is shared across all parallel agents — the first agent registers,
    # and we never unregister during the run (cleanup happens at pool level).
    cli_mcp_registered = False
    if mcp_style == "cli-register" and cfg.jsonl_file is not None:
        name = _register_cli_mcp(ai_cmd, cfg, work_dir)
        cli_mcp_registered = name is not None

    args, mcp_config_path = _build_ai_cmd(prompt, cfg, work_dir=work_dir)
    env = _build_analysis_env(ai_cmd)
    stream_err = Path(str(stream_file) + ".err")

    try:
        process, timed_out = _spawn_and_monitor(
            args, work_dir, env, _SpawnPaths(stream_file, stream_err), cfg,
        )
    finally:
        if mcp_config_path is not None:
            mcp_config_path.unlink(missing_ok=True)
        # Don't unregister cli MCP here — other parallel agents may still need it.
        # Cleanup happens via _register_cli_mcp's idempotent remove-then-add on next run.

    if not timed_out:
        _check_process_result(process, stream_err)


def _resolve_provider_config(
    cfg: AnalysisConfig, env: Mapping[str, str],
) -> tuple[str, str, str]:
    """Look up model, api_base, and api_key from provider config.

    Credentials come from *env*, injected by the public entry point
    (``run_analysis``) so this resolution logic never touches process-global
    environment state itself.

    Raises AnalysisError if model or api_base are missing.
    """
    ai_cmd = cfg.ai_cmd or get_ai_cmd()
    configs = get_provider_configs()
    provider_cfg = configs.get(ai_cmd, {})

    model = cfg.ai_model or provider_cfg.get("model", "")
    api_base = provider_cfg.get("api_base", "")
    api_key_env = provider_cfg.get("api_key_env", "")
    api_key = env.get(api_key_env, "") if api_key_env else ""
    if not api_key:
        loader = _CREDENTIAL_LOADERS.get(ai_cmd)
        if loader is not None:
            api_key = loader() or ""

    if not model:
        raise AnalysisError(
            f"No model configured for provider '{ai_cmd}'. "
            f"Go to Settings in the dashboard to select a model, or set AI_MODEL in your environment."
        )
    if not api_base:
        raise AnalysisError(
            f"No API base URL configured for provider '{ai_cmd}'. "
            f"Go to Settings in the dashboard to configure it, or set the URL in ai_providers.json."
        )
    if not api_key and provider_cfg.get("api_key_required"):
        # Defense in depth for entry points that skip check_evaluate_prereqs:
        # fail with a clear message instead of 401s on every request mid-run.
        raise AnalysisError(
            f"No API key found for provider '{ai_cmd}'. "
            f"Set the {api_key_env or 'API key'} environment variable, "
            f"or configure the key in the dashboard Settings."
        )
    return model, api_base, api_key


def _dispatch_one_batch(
    batch: list[Path], work_dir: Path, jsonl_file: Path, standards_text: str,
    trust_model: TrustModel, cfg: AnalysisConfig, model: str, api_base: str, api_key: str,
) -> None:
    """Assemble the API prompt for one size-budgeted batch and dispatch it.

    Split out of the per-batch loop in _run_api_analysis_bridge so the bridge
    itself stays a thin cancellation/orchestration loop.
    """
    from quodeq.analysis import _api_runner

    api_prompt = assemble_api_prompt(
        source_files=batch,
        standards_text=standards_text,
        dimension=cfg.dimension or "general",
        repo_name=str(work_dir.name),
        repo_root=work_dir,
        trust_model=trust_model,
    )

    # POSIX-style separators: paths flow into findings (file fields,
    # downstream JSONL projection) and into the prompt; the rest of the
    # pipeline assumes forward slashes (path-role classifier, enrichment,
    # SQLite store). Backslashes on Windows would break those joins.
    rel_paths = [f.relative_to(work_dir).as_posix() for f in batch]
    _api_runner.run_api_analysis(
        prompt=api_prompt,
        jsonl_file=jsonl_file,
        config=_api_runner.ApiRunnerConfig(
            model=model,
            api_base=api_base,
            api_key=api_key,
            context_size=cfg.context_size,
            n_subagents=max(
                1, getattr(getattr(cfg.run_config, "options", None), "max_subagents", 1),
            ),
        ),
        compiled_dir=cfg.compiled_dir,
        dimension=cfg.dimension,
        work_dir=work_dir,
        source_file_paths=rel_paths,
        # Wire the synchronous cache-write closure when the pool layer
        # supplied a RunConfig carrier. Legacy callers pass nothing and
        # the API runner simply skips the cache write.
        run_config=cfg.run_config,
        dim_id=cfg.dimension,
    )


def _run_api_analysis_bridge(
    work_dir: Path, prompt: str, stream_file: Path, cfg: AnalysisConfig,
    env: Mapping[str, str],
) -> None:
    """Run analysis via direct API call (new behavior).

    Builds its own prompt using assemble_api_prompt() instead of the CLI
    prompt, which contains MCP tool-use instructions that confuse API models.
    Files are dispatched in size-budgeted sub-batches (one model call each)
    so a batch of large files cannot overflow the model context.
    """
    model, api_base, api_key = _resolve_provider_config(cfg, env)

    jsonl_file = cfg.jsonl_file
    if jsonl_file is None:
        jsonl_file = Path(str(stream_file).replace(".stream", "_evidence.jsonl"))

    source_files = _gather_api_source_files(work_dir, cfg, jsonl_file, stream_file)
    if source_files is None:
        return

    from quodeq.data.fs.standards_prefs import load_project_overrides  # noqa: PLC0415

    overrides = load_project_overrides(work_dir)
    standards_text = _load_standards_text(cfg.compiled_dir, cfg.dimension, overrides=overrides)
    # Resolved once per dimension, not per batch: same declared-then-detected
    # trust model the finding sink applies (quodeq.context.trust_model),
    # briefed here so the model generates fewer out-of-scope findings for the
    # sink to have to claw back.
    trust_model = resolve_trust_model(work_dir)

    for batch in _batch_files_by_size(source_files, _api_prompt_char_budget()):
        # A cancelled run (signal, breaker, fatal provider error) must not
        # keep burning model calls on the remaining batches.
        if cancellation.is_cancelled():
            _log.info("Cancellation requested -- stopping API batch dispatch")
            break
        _dispatch_one_batch(
            batch, work_dir, jsonl_file, standards_text, trust_model,
            cfg, model, api_base, api_key,
        )

    stream_file.write_text('{"type":"api_runner","status":"complete"}\n', encoding="utf-8")
    _log.debug("API analysis complete, evidence written to %s", jsonl_file)


def run_analysis(
    work_dir: Path, prompt: str, stream_file: Path,
    config: AnalysisConfig | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    """Run AI analysis, dispatching to CLI or API runner based on provider type.

    *env* supplies provider credentials; the default is resolved here, at the
    public boundary, so the resolution logic below stays injectable.
    """
    cfg = config or AnalysisConfig()
    ai_cmd = cfg.ai_cmd or get_ai_cmd()
    provider_type = _get_provider_type(ai_cmd)

    if provider_type == "api":
        _run_api_analysis_bridge(work_dir, prompt, stream_file, cfg,
                                 os.environ if env is None else env)
    else:
        _run_cli_analysis(work_dir, prompt, stream_file, cfg)
