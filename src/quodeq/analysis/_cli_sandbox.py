"""OS sandbox for agent CLIs whose own approvals/sandbox an analysis run bypasses.

Codex cancels MCP tool calls under its own sandbox, so it runs with
--dangerously-bypass-approvals-and-sandbox; Gemini's plan mode is overridden
in folders it does not trust. Either way the CLI keeps tools a
prompt-injected repo could steer, so it runs inside an OS sandbox Quodeq
controls: writes only to this project's evaluations, the run's queue, the
result cache, the CLI's own home and temp; no reads of file contents under
the user's home except those, the analysed repo, the standards and what the
CLI and the findings server need to run; and no connections to services on
this machine (Quodeq's own API), except a local proxy.

Quodeq's other state stays out of reach on purpose: other projects' clones
and evidence, the assistant database and the settings of other projects.

Where no OS sandbox works (Windows, a container, Linux without a usable
bubblewrap or firejail) the scan still runs, as it did before the sandbox
existed, with the limits that need none: the env allowlist and, for Codex,
the dedicated home without account apps, plugins or the user's MCP
servers. *require_sandbox* makes it fail instead.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from quodeq.analysis.codex_sandbox import (
    native_args, native_sandbox_works, plain_read_only_args, profile_args,
)
from quodeq.analysis._config import AnalysisConfig
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.data.fs.project_standards import project_settings_file, settings_reports_root
from quodeq.shared.codex_home import user_codex_auth_file
from quodeq.shared.os_sandbox import (
    SandboxUnavailable,
    external_sandbox_prefix,
    loopback_proxy_ports,
    runtime_readable_dirs,
)

_warned_unsandboxed: set[str] = set()  # one warning per CLI per process, not per agent spawn


@dataclass(frozen=True)
class SandboxPolicy:
    """What a scan does where no OS sandbox works: warn on *log* and run
    without one, or, with *require*, fail."""

    require: bool = False
    log: LogSink = field(default=NULL_LOG)


def _project_dir(cfg: AnalysisConfig) -> Path | None:
    """``<reports>/<project>`` for ``<project>/<run>/evidence/<dim>_evidence.jsonl``."""
    if cfg.jsonl_file is None:
        return None
    return cfg.jsonl_file.resolve().parent.parent.parent


def _run_writable_dirs(cfg: AnalysisConfig) -> list[Path]:
    """Where the findings server writes: the project's evaluations (the run's
    evidence and events, and the precedent reads of its earlier runs, whose
    SQLite files need their -shm alongside), the queue and the cache."""
    dirs: list[Path] = []
    if (project := _project_dir(cfg)) is not None:
        dirs.append(project)
    if cfg.queue_path is not None:
        dirs.append(cfg.queue_path.resolve().parent)
    if cfg.cache_root is not None:
        dirs.append(Path(cfg.cache_root).resolve())
    return dirs


def _settings_dir(cfg: AnalysisConfig) -> list[Path]:
    """The dir of the standards settings the findings server reads (a scoped
    child reads its parent project's)."""
    project = _project_dir(cfg)
    if project is None or not project.name:
        return []
    return [project_settings_file(settings_reports_root(), project.name, migrate=False).parent]


def _readable_dirs(cfg: AnalysisConfig, work_dir: Path, binary: str) -> list[Path]:
    dirs = [work_dir.resolve(), *runtime_readable_dirs(binary), *_settings_dir(cfg)]
    if cfg.compiled_dir is not None:
        # The standards root (compiled/'s parent) keys the findings cache.
        compiled = Path(cfg.compiled_dir).resolve()
        dirs += [compiled, compiled.parent]
    return dirs


def _cli_home(spec: dict, env: Mapping[str, str]) -> Path:
    """The CLI's own state dir: from an env var Quodeq set (Codex's dedicated
    home), else a path under the user's home."""
    if (var := spec.get("cli_home_env")) and env.get(var):
        return Path(env[var])
    return Path.home() / spec["cli_home"]


def analysis_sandbox_prefix(
    cfg: AnalysisConfig, provider_cfg: dict, work_dir: Path, binary: str,
    env: Mapping[str, str] | None = None, policy: SandboxPolicy = SandboxPolicy(),
) -> tuple[list[str], Callable[[], None]]:
    """The sandbox launcher prefix for this run's CLI, or ``([], no-op)`` when
    the provider declares no ``analysis_sandbox`` or no sandbox works here.
    *env* is the CLI's env.

    Raises SandboxUnavailable instead of running unsandboxed when
    ``policy.require`` is set.
    """
    spec = provider_cfg.get("analysis_sandbox")
    if not spec:
        return [], lambda: None
    env = env or {}
    cli_home = _cli_home(spec, env)
    cli_home.mkdir(parents=True, exist_ok=True)
    writable = [cli_home, *_run_writable_dirs(cfg)]
    try:
        return _sandbox_prefix(cfg, work_dir, binary, env, writable)
    except SandboxUnavailable as exc:
        if policy.require:
            raise
        if binary not in _warned_unsandboxed:
            _warned_unsandboxed.add(binary)
            policy.log.warning(f"Running {binary} without an OS sandbox: {exc} "
                        "Set QUODEQ_REQUIRE_SANDBOX=1 to fail instead.")
        return [], lambda: None


def _sandbox_prefix(
    cfg: AnalysisConfig, work_dir: Path, binary: str, env: Mapping[str, str], writable: list[Path],
) -> tuple[list[str], Callable[[], None]]:
    # The dedicated Codex home links to the user's login, which Codex rewrites
    # on refresh: that one file, not the user's ~/.codex.
    auth = user_codex_auth_file(env)
    return external_sandbox_prefix(
        writable_dirs=[str(d) for d in writable],
        writable_files=[str(auth)] if auth else [],
        readable_home_dirs=[str(d) for d in _readable_dirs(cfg, work_dir, binary)],
        readonly_dirs=[str(work_dir.resolve())],
        block_loopback=True,
        loopback_allow_ports=loopback_proxy_ports(env),
    )


def confine_cli(
    cfg: AnalysisConfig, provider_cfg: dict, work_dir: Path, args: list[str],
    env: Mapping[str, str], policy: SandboxPolicy = SandboxPolicy(),
) -> tuple[list[str], Callable[[], None]]:
    """*args* confined as well as this machine allows: the CLI's own sandbox
    where the provider has one that works here (Codex), else the OS sandbox,
    else, unless *policy* requires one, unconfined."""
    if provider_cfg.get("native_sandbox") and (native := _native_args(cfg, work_dir, args, env)):
        return native, lambda: None
    prefix, cleanup = analysis_sandbox_prefix(cfg, provider_cfg, work_dir, args[0], env, policy)
    return [*prefix, *args], cleanup


def _native_args(
    cfg: AnalysisConfig, work_dir: Path, args: list[str], env: Mapping[str, str],
) -> list[str] | None:
    project = _project_dir(cfg)
    sample = next((p for p in sorted(work_dir.iterdir()) if p.is_file()), None)
    if project is None or sample is None:
        return None
    readable = [work_dir.resolve(), project, *runtime_readable_dirs("rg")]
    evidence = cfg.jsonl_file.resolve().parent if cfg.jsonl_file else project
    # Home unreadable where Codex can enforce it, else plain read-only (no
    # writes, no network), which still beats the OS fallbacks on Windows.
    for profile in (profile_args(Path.home().resolve(), readable), plain_read_only_args()):
        if native_sandbox_works(args[0], profile, evidence, sample.resolve(), env):
            return native_args(args, profile)
    return None
