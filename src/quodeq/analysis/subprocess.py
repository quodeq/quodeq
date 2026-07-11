"""AI analysis runner -- dispatches to CLI subprocess or API runner.

This module is the public entry point. Implementation is split across:
- _config.py:      AnalysisConfig, HeartbeatCallback, dataclasses
- _mcp_config.py:  MCP config file creation
- _command.py:     CLI argument and environment construction
- _process.py:     Process spawning, heartbeat, error handling
- _api_runner.py:  OpenAI SDK-based direct API runner
"""
from __future__ import annotations

import json as _json
import logging
import os
from collections.abc import Callable
from pathlib import Path

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
from quodeq.analysis.subagents.file_queue import FileQueue
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


_MAX_API_PROMPT_CHARS = int(os.environ.get("QUODEQ_MAX_API_PROMPT_CHARS", "30000"))  # Target prompt size for local models (~8K tokens)
_MAX_API_FILE_SIZE = int(os.environ.get("QUODEQ_MAX_API_FILE_SIZE", "15000"))  # Skip files larger than 15KB


def _load_skip_dirs() -> frozenset[str]:
    """Load skip_dirs from detection.json (shared with manifest builder)."""
    try:
        det_path = Path(__file__).resolve().parent.parent / "data" / "config" / "detection.json"
        data = _json.loads(det_path.read_text(encoding="utf-8"))
        return frozenset(data.get("skip_dirs", []))
    except (OSError, _json.JSONDecodeError):
        return frozenset({"node_modules", ".git", "__pycache__", "venv", ".venv", "dist", "build"})


_SKIP_DIRS = _load_skip_dirs()
# Code files first, style/markup last
_CODE_EXTS = frozenset({".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".rb", ".php", ".c", ".cpp", ".h", ".cs", ".swift", ".kt"})
_MARKUP_EXTS = frozenset({".html", ".css", ".scss", ".vue", ".svelte"})


def _gather_source_files(work_dir: Path) -> list[Path]:
    """Collect source files from work_dir for API prompt assembly.

    Prioritizes code files over markup/styles and caps total size to
    fit within local model context limits.
    """
    _ALL_EXTS = _CODE_EXTS | _MARKUP_EXTS
    all_files: list[Path] = [
        f for f in work_dir.rglob("*") if f.is_file() and f.suffix in _ALL_EXTS
    ]
    # Cache stat results to avoid repeated syscalls on the same files
    stat_cache: dict[Path, int] = {}
    for f in all_files:
        try:
            stat_cache[f] = f.stat().st_size
        except OSError:
            pass

    # Filter out non-source dirs, dotdirs, empty files, and oversized files
    filtered = [
        f for f in all_files
        if f in stat_cache
        and not any(p in f.parts for p in _SKIP_DIRS)
        and not any(p.startswith(".") for p in f.relative_to(work_dir).parts)
        and 0 < stat_cache[f] < _MAX_API_FILE_SIZE
    ]
    # Prioritize code files over markup
    code_files = [f for f in filtered if f.suffix in _CODE_EXTS]
    markup_files = [f for f in filtered if f.suffix in _MARKUP_EXTS]
    # Within each group, sort by size (moderate files first — not too small, not too big)
    code_files.sort(key=lambda f: stat_cache[f], reverse=True)
    markup_files.sort(key=lambda f: stat_cache[f], reverse=True)

    # Fill up to the prompt char budget
    selected: list[Path] = []
    total_chars = 0
    for f in code_files + markup_files:
        size = stat_cache[f]
        if total_chars + size > _MAX_API_PROMPT_CHARS:
            continue
        selected.append(f)
        total_chars += size

    _log.debug("Selected %d files (%d chars) from %d candidates for API prompt",
              len(selected), total_chars, len(filtered))
    return selected


_MAX_STANDARDS_CHARS = int(os.environ.get("QUODEQ_MAX_STANDARDS_CHARS", "50000"))  # Allow full standards for models with large context


def _load_standards_text(
    compiled_dir: Path | None,
    dimension: str | None,
    overrides: dict | None = None,
) -> str:
    """Load compiled standards as structured JSON for the API prompt.

    Renders from the compiled JSON as a compact JSON array grouped by principle,
    so API models see explicit structure instead of a flat requirement list.
    Falls back to the .md file if JSON is unavailable.

    *overrides* is the per-project threshold override map from
    :func:`quodeq.core.standards.overrides.load_project_overrides`.  When
    supplied, placeholder templates in requirement text are resolved before
    the text is sent to the model.

    Truncates to _MAX_STANDARDS_CHARS to keep prompts within context limits.
    """
    if not compiled_dir or not dimension:
        return ""
    json_path = compiled_dir / f"{dimension}.json"
    if json_path.exists():
        try:
            data = _json.loads(json_path.read_text(encoding="utf-8"))
            text = _render_standards_grouped(data, overrides=overrides)
            if text:
                if len(text) > _MAX_STANDARDS_CHARS:
                    _log.info("Truncating %s standards from %d to %d chars for API prompt",
                              dimension, len(text), _MAX_STANDARDS_CHARS)
                    text = text[:_MAX_STANDARDS_CHARS] + "\n\n[... standards truncated for context limits ...]"
                return text
        except (OSError, _json.JSONDecodeError):
            pass
    md_path = compiled_dir / f"{dimension}.md"
    if md_path.exists():
        try:
            text = md_path.read_text(encoding="utf-8")
            if len(text) > _MAX_STANDARDS_CHARS:
                text = text[:_MAX_STANDARDS_CHARS] + "\n\n[... standards truncated for context limits ...]"
            return text
        except OSError:
            pass
    return ""


def _render_standards_grouped(data: dict, overrides: dict | None = None) -> str:
    """Render standards as a compact JSON array grouped by principle.

    The explicit structure helps local models give attention to ALL principle
    groups instead of fixating on the first ones in a flat list.

    *overrides* is the per-project ``{req_id: {param: value}}`` map produced
    by :func:`quodeq.core.standards.overrides.load_project_overrides`.  When
    present, each requirement's text template is resolved before being emitted
    so that models never receive raw ``{placeholder}`` strings.
    """
    from quodeq.core.standards.overrides import resolve_requirement_text  # noqa: PLC0415

    principles = data.get("principles", [])
    if not principles:
        return ""
    checklist = []
    for p in principles:
        checklist.append({
            "principle": p.get("name", "Unknown"),
            "requirements": [
                {"id": r["id"], "rule": resolve_requirement_text(r, (overrides or {}).get(r["id"]))}
                for r in p.get("requirements", [])
            ],
        })
    return _json.dumps(checklist, separators=(",", ":"))


def _read_omlx_key() -> str | None:
    from quodeq.llm_bridge._omlx import _read_omlx_api_key  # noqa: PLC0415
    return _read_omlx_api_key()


# Registry of provider-specific credential loaders. Each callable returns the
# API key string (or None/empty string) for that provider. New providers can
# be added here without touching _resolve_provider_config.
_CREDENTIAL_LOADERS: dict[str, Callable[[], str | None]] = {
    "omlx": _read_omlx_key,
}


def _resolve_provider_config(cfg: AnalysisConfig) -> tuple[str, str, str]:
    """Look up model, api_base, and api_key from provider config.

    Raises AnalysisError if model or api_base are missing.
    """
    ai_cmd = cfg.ai_cmd or get_ai_cmd()
    configs = get_provider_configs()
    provider_cfg = configs.get(ai_cmd, {})

    model = cfg.ai_model or provider_cfg.get("model", "")
    api_base = provider_cfg.get("api_base", "")
    api_key_env = provider_cfg.get("api_key_env", "")
    api_key = os.environ.get(api_key_env, "") if api_key_env else ""
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


def _gather_api_source_files(
    work_dir: Path, cfg: AnalysisConfig, jsonl_file: Path, stream_file: Path,
) -> list[Path] | None:
    """Gather source files from queue or by scanning.

    Returns None (and writes empty output) when the queue is exhausted.
    """
    if cfg.queue_path and cfg.queue_path.exists():
        queue = FileQueue(cfg.queue_path)
        taken = queue.take(count=min(cfg.max_files_per_agent or 10, 3), agent_id=cfg.agent_id)
        source_files = [
            work_dir / f for f in taken
            if (work_dir / f).exists() and (work_dir / f).stat().st_size < _MAX_API_FILE_SIZE
        ]
        _log.debug("Took %d files from queue for API analysis", len(source_files))
        if not source_files:
            # Don't touch jsonl_file — it's the SHARED `{dim}_evidence.jsonl`
            # that every agent in the pool appends to via MCP. Truncating it
            # here wipes findings from every other agent in the pool.
            stream_file.write_text('{"type":"api_runner","status":"complete"}\n', encoding="utf-8")
            return None
        return source_files
    return _gather_source_files(work_dir)


def _run_api_analysis_bridge(
    work_dir: Path, prompt: str, stream_file: Path, cfg: AnalysisConfig,
) -> None:
    """Run analysis via direct API call (new behavior).

    Builds its own prompt using assemble_api_prompt() instead of the CLI
    prompt, which contains MCP tool-use instructions that confuse API models.
    """
    from quodeq.analysis._api_runner import run_api_analysis, ApiRunnerConfig

    model, api_base, api_key = _resolve_provider_config(cfg)

    jsonl_file = cfg.jsonl_file
    if jsonl_file is None:
        jsonl_file = Path(str(stream_file).replace(".stream", "_evidence.jsonl"))

    source_files = _gather_api_source_files(work_dir, cfg, jsonl_file, stream_file)
    if source_files is None:
        return

    from quodeq.core.standards.overrides import load_project_overrides  # noqa: PLC0415

    overrides = load_project_overrides(work_dir)
    standards_text = _load_standards_text(cfg.compiled_dir, cfg.dimension, overrides=overrides)
    api_prompt = assemble_api_prompt(
        source_files=source_files,
        standards_text=standards_text,
        dimension=cfg.dimension or "general",
        repo_name=str(work_dir.name),
        repo_root=work_dir,
    )

    # POSIX-style separators: paths flow into findings (file fields,
    # downstream JSONL projection) and into the prompt; the rest of the
    # pipeline assumes forward slashes (path-role classifier, enrichment,
    # SQLite store). Backslashes on Windows would break those joins.
    rel_paths = [f.relative_to(work_dir).as_posix() for f in source_files]
    run_api_analysis(
        prompt=api_prompt,
        jsonl_file=jsonl_file,
        config=ApiRunnerConfig(
            model=model,
            api_base=api_base,
            api_key=api_key,
            context_size=cfg.context_size,
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

    stream_file.write_text('{"type":"api_runner","status":"complete"}\n', encoding="utf-8")
    _log.debug("API analysis complete, evidence written to %s", jsonl_file)


def run_analysis(
    work_dir: Path, prompt: str, stream_file: Path,
    config: AnalysisConfig | None = None,
) -> None:
    """Run AI analysis, dispatching to CLI or API runner based on provider type."""
    cfg = config or AnalysisConfig()
    ai_cmd = cfg.ai_cmd or get_ai_cmd()
    provider_type = _get_provider_type(ai_cmd)

    if provider_type == "api":
        _run_api_analysis_bridge(work_dir, prompt, stream_file, cfg)
    else:
        _run_cli_analysis(work_dir, prompt, stream_file, cfg)
