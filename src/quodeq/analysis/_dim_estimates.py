"""Compute per-dim file count estimates before any dim runs.

The dashboard uses these to render an accurate run total upfront, instead
of waiting for each dim to start and reveal its post-filter queue size
one at a time. The estimate matches what the queue will hold once the
dim actually runs, so the header total stays stable as dims transition
from pending → running.

Each estimate carries a short *reason* tag so the UI can flag inflated
counts that aren't really "this much code" but "catching up from a
previous run that died early":

  - "full"             — non-incremental run; estimate = full source list
  - "diff"             — diff filter active; estimate = filter intersection
  - "incremental"      — normal incremental; estimate = changed + dependents
  - "first-run"        — no prev fingerprint; estimate = full source list
  - "standards-changed" — standards file changed; full re-analysis
  - "prompts-changed"  — prompt files changed; full re-analysis
  - "catching-up"      — most files were fingerprinted but never analyzed
                          last time (pool timed out / cancelled), so they
                          get re-swept this run
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quodeq.analysis._incr_change_detection import detect_changed_files
from quodeq.analysis._incremental_phases import _list_all_source_files
from quodeq.analysis._types import RunConfig
from quodeq.analysis.fingerprint import find_previous_fingerprint
from quodeq.analysis.incremental import ClassificationInput, classify_files

DIM_ESTIMATES_FILENAME = "dim_estimates.json"

# Below this fraction, the previous run is considered to have died early and
# this dim is "catching up" (most files re-swept via the not_analyzed branch).
_CATCHING_UP_PREV_ANALYZED_RATIO = 0.5


def _classify_full_reanalysis_reason(detection_reason: str) -> str:
    if "standards" in detection_reason:
        return "standards-changed"
    if "prompts" in detection_reason:
        return "prompts-changed"
    if "no previous fingerprint" in detection_reason:
        return "first-run"
    return "first-run"


def compute_dim_estimates(
    config: RunConfig, dimensions: list[str],
) -> dict[str, dict[str, Any]]:
    """Estimate per-dim file count + reason, before any dim runs.

    Returns ``{dim_id: {"count": int, "reason": str}}``. See module docstring
    for the reason vocabulary.
    """
    estimates: dict[str, dict[str, Any]] = {}
    evidence_dir = config.work_dir or config.src
    file_filter = config.options.incremental_file_filter
    for dim_id in dimensions:
        files = _list_all_source_files(config, dim_id)
        if not files:
            estimates[dim_id] = {"count": 0, "reason": "empty"}
            continue
        if config.options.incremental:
            prev_fp, _ = find_previous_fingerprint(evidence_dir, dim_id)
            detection = detect_changed_files(
                config.src, files, prev_fp, config.standards_dir, dim_id,
            )
            classification = classify_files(
                inputs=ClassificationInput(
                    src=config.src, files=files, prev_fingerprint=prev_fp,
                    standards_dir=config.standards_dir, dimension=dim_id,
                    language=config.language,
                ),
            )
            count = len(classification.to_analyze)
            if detection.full_reanalysis:
                reason = _classify_full_reanalysis_reason(detection.reason)
            else:
                prev_analyzed = len(prev_fp.get("analyzed_files", [])) if prev_fp else 0
                prev_files = len(prev_fp.get("file_hashes", {})) if prev_fp else 0
                if (
                    prev_files > 0
                    and prev_analyzed < prev_files * _CATCHING_UP_PREV_ANALYZED_RATIO
                ):
                    reason = "catching-up"
                else:
                    reason = "incremental"
            estimates[dim_id] = {"count": count, "reason": reason}
        elif file_filter is not None:
            count = sum(1 for f in files if f in file_filter)
            estimates[dim_id] = {"count": count, "reason": "diff"}
        else:
            estimates[dim_id] = {"count": len(files), "reason": "full"}
    return estimates


def write_dim_estimates(
    run_dir: Path, estimates: dict[str, dict[str, Any]],
) -> None:
    """Persist per-dim estimates next to status.json. Best-effort."""
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / DIM_ESTIMATES_FILENAME).write_text(
            json.dumps(estimates, indent=2), encoding="utf-8",
        )
    except OSError:
        pass


def read_dim_estimates(run_dir: Path) -> dict[str, dict[str, Any]]:
    """Return per-dim estimates from disk, or {} if missing/corrupt.

    Each value is normalised to ``{"count": int, "reason": str}``.
    """
    path = run_dir / DIM_ESTIMATES_FILENAME
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError):
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for k, v in data.items():
        # Current format: {"count": int, "reason": str}.
        if isinstance(v, dict) and isinstance(v.get("count"), int):
            out[k] = {"count": v["count"], "reason": str(v.get("reason", ""))}
        # Legacy format: a bare int. Older runs predate the reason tag.
        elif isinstance(v, int):
            out[k] = {"count": v, "reason": ""}
    return out
