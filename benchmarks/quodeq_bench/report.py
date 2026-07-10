"""Build, persist, average, and render benchmark reports."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from quodeq_bench.metrics import DimensionMetrics


def collect_meta(repo_root: Path, provider: str, model: str, reps: int) -> dict:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    digest = hashlib.sha256()
    prompts_dir = repo_root / "src" / "quodeq" / "data" / "prompts"
    for path in sorted(prompts_dir.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(prompts_dir)).encode())
            digest.update(path.read_bytes())
    return {
        "provider": provider,
        "model": model,
        "reps": reps,
        "quodeq_commit": commit,
        "prompts_hash": digest.hexdigest(),
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def build_report(
    meta: dict, metrics: dict[str, DimensionMetrics], errored: bool = False
) -> dict:
    return {
        "meta": meta,
        "errored": errored,
        "metrics": {dim: m.as_dict() for dim, m in sorted(metrics.items())},
    }


def _avg(values: list[float | int]) -> float | int:
    mean = round(sum(values) / len(values), 4)
    if all(isinstance(v, int) for v in values) and float(mean).is_integer():
        return int(mean)
    return mean


def average_reports(reports: list[dict]) -> dict:
    if not reports:
        raise ValueError("no reports to average")
    dims = sorted({dim for r in reports for dim in r["metrics"]})
    averaged: dict[str, dict] = {}
    for dim in dims:
        rows = [r["metrics"][dim] for r in reports if dim in r["metrics"]]
        keys = rows[0].keys()
        averaged[dim] = {
            key: _avg([row[key] for row in rows]) for key in keys
        }
    return {
        "meta": reports[0]["meta"],
        "errored": any(r.get("errored") for r in reports),
        "metrics": averaged,
    }


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def load_report(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def to_markdown(report: dict) -> str:
    meta = report["meta"]
    lines = [
        f"### Benchmark: {meta.get('provider')} / {meta.get('model')}",
        "",
        "| Dimension | Precision | Recall | F1 | FP/KLOC | Labels |",
        "|---|---|---|---|---|---|",
    ]
    for dim, m in report["metrics"].items():
        lines.append(
            f"| {dim} | {m['precision']} | {m['recall']} | {m['f1']} "
            f"| {m['fp_density']} | {m['total_labels']} |"
        )
    return "\n".join(lines) + "\n"
