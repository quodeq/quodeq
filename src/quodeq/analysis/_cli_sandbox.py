"""OS sandbox for agent CLIs whose own approvals/sandbox an analysis run bypasses.

Codex cancels MCP tool calls under its own sandbox, so it runs with
--dangerously-bypass-approvals-and-sandbox; Gemini's plan mode is overridden
in folders it does not trust. Either way the CLI keeps tools a
prompt-injected repo could steer, so it runs inside an OS sandbox Quodeq
controls: no writes outside Quodeq's state, the CLI's own home and temp, and
no reads of file contents under the user's home except the analysed repo,
Quodeq's state and what the CLI and the findings server need to run.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from quodeq.analysis._config import AnalysisConfig
from quodeq.shared.env_paths import get_quodeq_dir
from quodeq.shared.os_sandbox import external_sandbox_prefix, runtime_readable_dirs


def _run_writable_dirs(cfg: AnalysisConfig) -> list[Path]:
    """Where the findings server writes: the run dir, the queue and the cache."""
    dirs: list[Path] = []
    if cfg.jsonl_file is not None:
        # <run_dir>/evidence/<dim>_evidence.jsonl, and events.jsonl in run_dir
        dirs.append(cfg.jsonl_file.resolve().parent.parent)
    if cfg.queue_path is not None:
        dirs.append(cfg.queue_path.resolve().parent)
    if cfg.cache_root is not None:
        dirs.append(Path(cfg.cache_root).resolve())
    return dirs


def _readable_dirs(cfg: AnalysisConfig, work_dir: Path, binary: str) -> list[Path]:
    dirs = [work_dir.resolve(), *runtime_readable_dirs(binary)]
    if cfg.compiled_dir is not None:
        dirs.append(Path(cfg.compiled_dir).resolve())
    return dirs


def analysis_sandbox_prefix(
    cfg: AnalysisConfig, provider_cfg: dict, work_dir: Path, binary: str,
) -> tuple[list[str], Callable[[], None]]:
    """The sandbox launcher prefix for this run's CLI, or ``([], no-op)`` when
    the provider declares no ``analysis_sandbox``.

    Raises RuntimeError when the platform has no usable sandbox, so a CLI
    with bypassed approvals never runs unconfined.
    """
    spec = provider_cfg.get("analysis_sandbox")
    if not spec:
        return [], lambda: None
    cli_home = Path.home() / spec["cli_home"]
    cli_home.mkdir(parents=True, exist_ok=True)
    writable = [get_quodeq_dir(), cli_home, *_run_writable_dirs(cfg)]
    return external_sandbox_prefix(
        writable_dirs=[str(d) for d in writable],
        writable_files=[],
        readable_home_dirs=[str(d) for d in _readable_dirs(cfg, work_dir, binary)],
        readonly_dirs=[str(work_dir.resolve())],
    )
