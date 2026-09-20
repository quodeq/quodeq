"""Builders shared by the test_dimension_helpers* siblings."""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis.run_types import AnalysisOptions, RunConfig
from quodeq.analysis.cache._persist_watcher import CachePersistProvenance


def _write_files(root: Path, contents: dict[str, str]) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in contents.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return sorted(contents.keys())


def _make_config(
    src: Path, *, work_dir: Path | None = None,
    standards_dir: Path | None = None, model: str = "test-model",
    language: str = "python",
) -> RunConfig:
    opts = AnalysisOptions(subagent_model=model)
    return RunConfig(
        src=src, language=language, standards_dir=standards_dir,
        work_dir=work_dir or src, options=opts,
    )


def _write_compiled_standards(standards_dir: Path, dim: str, payload: str) -> None:
    compiled = standards_dir / "compiled"
    compiled.mkdir(parents=True, exist_ok=True)
    (compiled / f"{dim}.json").write_text(payload)


def _write_project_overrides(src: Path, payload: str) -> None:
    path = src / ".quodeq" / "standards-overrides.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)


def _hash_inputs(config: RunConfig, dimension: str) -> CachePersistProvenance:
    """Compute the provenance hash inputs persist_dispatch_results now
    expects the caller to hoist and pass in."""
    from quodeq.analysis.cache._key_provenance import _hash_prompts_combined
    from quodeq.analysis.fingerprint import _hash_standards, dimension_params_state

    standards_hash = (
        _hash_standards(config.standards_dir, dimension, config.src)
        if config.standards_dir else ""
    ) or ""
    params_hash, effective_params = dimension_params_state(
        config.standards_dir, dimension, config.src,
    )
    prompts_hash = _hash_prompts_combined(config.prompts_dir)
    return CachePersistProvenance(
        standards_hash=standards_hash, params_hash=params_hash,
        effective_params=effective_params, prompts_hash=prompts_hash,
    )
