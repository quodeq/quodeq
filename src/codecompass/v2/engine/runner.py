from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codecompass.v2.engine.evidence import Evidence


@dataclass
class RunConfig:
    src: Path
    plugin_id: str
    evaluators_dir: Path
    standards_dir: Path | None = None
    source_file_count: int = 0
    ai_caller: object = None


def run(config: RunConfig) -> Evidence:
    """Orchestrator: load plugin → analyse → Evidence.

    Pending rewrite in PR6 (AI-driven exploration pipeline).
    """
    plugin_dir = config.evaluators_dir / config.plugin_id
    if not plugin_dir.exists():
        raise ValueError(f"Plugin directory not found: {plugin_dir}")
    raise NotImplementedError("Runner rewrite pending PR6")


def detect_plugin(src: Path, evaluators_dir: Path) -> str:
    """Auto-detect the best plugin for a repository by counting extension matches.

    Reads each plugin.json under evaluators_dir, walks the repo counting files
    that match ``detects.extensions``, and returns the plugin_id with the most hits.
    Raises ValueError if no plugin matches any file.
    """
    import json

    best_id: str | None = None
    best_count = 0

    for child in sorted(evaluators_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        pf = child / "plugin.json"
        if not pf.exists():
            continue
        try:
            data = json.loads(pf.read_text())
        except (json.JSONDecodeError, KeyError):
            continue
        exts = set(data.get("detects", {}).get("extensions", []))
        if not exts:
            continue
        count = count_source_files(src, exts)
        if count > best_count:
            best_count = count
            best_id = data.get("id", child.name)

    if best_id is None:
        raise ValueError(
            f"No plugin in {evaluators_dir} matched any file in {src}"
        )
    return best_id


def count_source_files(src: Path, extensions: set[str]) -> int:
    """Count files under *src* whose suffix is in *extensions*."""
    total = 0
    for p in src.rglob("*"):
        if p.is_file() and p.suffix in extensions:
            total += 1
    return total


def run_full(config: RunConfig, output_dir: Path, mode: str = "numerical") -> dict:
    """Full pipeline: run → score → write reports. Returns scores dict.

    Pending rewrite in PR6 (AI-driven exploration pipeline).
    """
    raise NotImplementedError("Runner rewrite pending PR6")
