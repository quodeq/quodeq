"""Per-dimension batch context and dispatch loop for the direct API runner.

``subprocess.py``'s ``_run_api_analysis_bridge`` is the caller: it resolves
provider credentials, then hands off here to build the batch context
(``_build_api_batch_context``), the shared runner config
(``_build_batch_api_config``) and to dispatch the size-budgeted sub-batches
(``_dispatch_api_batches``, one model call per batch via
``_dispatch_one_batch``).

This module is a leaf of ``subprocess.py``: it must never import back from
it. ``assemble_api_prompt`` is bound here rather than there, so tests that
intercept the prompt patch ``quodeq.analysis._api_batch.assemble_api_prompt``
-- ``mock.patch`` resolves where a name is used.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from quodeq.analysis._api_source_gathering import (
    _batch_files_by_size,
    _gather_api_source_files,
)
from quodeq.analysis._api_standards_text import (
    _api_prompt_char_budget,
    _load_standards_text,
    _max_standards_chars,
)
from quodeq.analysis._config import AnalysisConfig
from quodeq.analysis.api_prompt_assembly import assemble_api_prompt
from quodeq.context.trust_model import TrustModel, resolve_trust_model
from quodeq.shared import cancellation

if TYPE_CHECKING:
    from quodeq.analysis._api_call import ApiRunnerConfig

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _BatchContext:
    """Per-dimension inputs shared by every batch, built once by
    ``_build_api_batch_context`` and reused by ``_dispatch_one_batch``.
    """

    work_dir: Path
    jsonl_file: Path
    standards_text: str
    trust_model: TrustModel | None
    source_files: list[Path]


def _build_api_batch_context(
    work_dir: Path, cfg: AnalysisConfig, env: Mapping[str, str], stream_file: Path,
) -> _BatchContext | None:
    """Resolve the per-dimension batch inputs, or None when the queue is
    exhausted (``_gather_api_source_files`` has already written the stream's
    complete marker in that case)."""
    jsonl_file = cfg.jsonl_file
    if jsonl_file is None:
        jsonl_file = Path(str(stream_file).replace(".stream", "_evidence.jsonl"))

    source_files = _gather_api_source_files(work_dir, cfg, jsonl_file, stream_file)
    if source_files is None:
        return None

    from quodeq.data.fs.standards_prefs import load_project_overrides  # noqa: PLC0415

    overrides = load_project_overrides(work_dir)
    # env is the resolved process environment (run_analysis defaults it to
    # os.environ), passed explicitly so these lookups skip os.environ itself.
    standards_text = _load_standards_text(
        cfg.compiled_dir, cfg.dimension, overrides=overrides,
        max_chars=_max_standards_chars(env),
    )
    # Resolved once per dimension: the same declared-then-detected trust
    # model the finding sink applies, briefed here to cut out-of-scope findings.
    trust_model = resolve_trust_model(work_dir)
    return _BatchContext(work_dir, jsonl_file, standards_text, trust_model, source_files)


def _dispatch_one_batch(
    batch: list[Path], ctx: _BatchContext, cfg: AnalysisConfig, api_config: ApiRunnerConfig,
) -> None:
    """Assemble the API prompt for one size-budgeted batch and dispatch it.

    Split out of _dispatch_api_batches so that loop itself stays a thin
    cancellation/orchestration step.
    """
    from quodeq.analysis import _api_runner

    api_prompt = assemble_api_prompt(
        source_files=batch,
        standards_text=ctx.standards_text,
        dimension=cfg.dimension or "general",
        repo_name=str(ctx.work_dir.name),
        repo_root=ctx.work_dir,
        trust_model=ctx.trust_model,
    )

    # POSIX-style separators: the rest of the pipeline assumes forward
    # slashes; backslashes on Windows would break those joins.
    rel_paths = [f.relative_to(ctx.work_dir).as_posix() for f in batch]
    _api_runner.run_api_analysis(
        request=_api_runner.ApiAnalysisRequest(
            prompt=api_prompt,
            jsonl_file=ctx.jsonl_file,
            compiled_dir=cfg.compiled_dir,
            dimension=cfg.dimension,
            work_dir=ctx.work_dir,
            source_file_paths=rel_paths,
            # None run_config (legacy callers) -> the API runner skips the cache write.
            run_config=cfg.run_config,
            dim_id=cfg.dimension,
        ),
        config=api_config,
    )


def _build_batch_api_config(
    cfg: AnalysisConfig, model: str, api_base: str, api_key: str,
) -> ApiRunnerConfig:
    """Build the one ApiRunnerConfig shared by every batch in a dimension."""
    from quodeq.analysis._api_runner import ApiRunnerConfig  # noqa: PLC0415

    max_subagents = getattr(getattr(cfg.run_config, "options", None), "max_subagents", 1)
    return ApiRunnerConfig(
        model=model, api_base=api_base, api_key=api_key,
        context_size=cfg.context_size, n_subagents=max(1, max_subagents),
    )


def _dispatch_api_batches(
    ctx: _BatchContext, cfg: AnalysisConfig, api_config: ApiRunnerConfig,
    env: Mapping[str, str],
) -> None:
    """Dispatch the dimension's files as size-budgeted sub-batches, one model
    call each, stopping as soon as the run is cancelled."""
    for batch in _batch_files_by_size(ctx.source_files, _api_prompt_char_budget(env)):
        # A cancelled run (signal, breaker, fatal provider error) must not
        # keep burning model calls on the remaining batches.
        if cancellation.is_cancelled():
            _log.info("Cancellation requested -- stopping API batch dispatch")
            break
        _dispatch_one_batch(batch, ctx, cfg, api_config)
