"""V2 Runner — orchestrates the AI-driven exploration pipeline.

Pipeline per dimension:
    1. Build prompt (prompt_builder)
    2. Run AI analysis (analysis.py — spawn AI CLI)
    3. Extract JSONL from stream
    4. Parse into Evidence (evidence_parser)
Merge per-dimension Evidence into a single Evidence object.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from codecompass.v2.engine.analysis import (
    extract_evidence_from_stream,
    is_stream_valid,
    run_analysis,
)
from codecompass.v2.engine.evidence import Evidence, PrincipleEvidence
from codecompass.v2.engine.evidence_parser import parse_jsonl_to_evidence
from codecompass.v2.engine.plugin_loader import load_plugin_full
from codecompass.v2.engine.prompt_builder import build_analysis_prompt, load_template


@dataclass
class RunConfig:
    src: Path
    plugin_id: str
    evaluators_dir: Path
    standards_dir: Path | None = None
    source_file_count: int = 0
    work_dir: Path | None = None
    analysis_budget: str | None = None
    heartbeat_callback: object | None = None
    template_path: Path | None = None
    dimensions: list[str] | None = None


def run(config: RunConfig) -> Evidence:
    """Orchestrate: load plugin → per-dimension AI analysis → merged Evidence."""
    plugin_dir = config.evaluators_dir / config.plugin_id
    if not plugin_dir.exists():
        raise ValueError(f"Plugin directory not found: {plugin_dir}")

    full = load_plugin_full(plugin_dir)
    template = load_template(config.template_path)
    date_str = date.today().isoformat()

    analysis_file = plugin_dir / "knowledge" / "analysis.md"
    analysis_md = analysis_file.read_text() if analysis_file.exists() else ""

    all_dims = [d["id"] for d in full["dimensions"].get("applies", [])]
    if config.dimensions:
        dimensions = [d for d in all_dims if d in config.dimensions]
    else:
        dimensions = all_dims
    work_dir = config.work_dir or config.src

    all_evidence: list[Evidence] = []
    total = len(dimensions)

    def _default_heartbeat(dim_name, src_count):
        def _cb(elapsed, progress):
            mins = elapsed // 60
            files = progress.get("files_read", 0)
            evidence = progress.get("evidence", 0)
            if src_count > 0:
                pct = min(round(files / src_count * 100), 100)
                print(f"  {dim_name}: {mins}m elapsed — {files} files read ({pct}%), {evidence} findings", flush=True)
            else:
                print(f"  {dim_name}: {mins}m elapsed — {files} files read, {evidence} findings", flush=True)
        return _cb

    for idx, dimension in enumerate(dimensions, 1):
        print(f"[{idx}/{total}] Analyzing {dimension}...", flush=True)
        prompt = build_analysis_prompt(
            template,
            plugin_id=config.plugin_id,
            repo_name=str(config.src),
            date_str=date_str,
            dimension=dimension,
            source_file_count=config.source_file_count,
            practices_data=full["practices"],
            dimensions_data=full["dimensions"],
            analysis_md=analysis_md,
            standards_dir=config.standards_dir,
        )

        stream_file = work_dir / f"{dimension}_live.stream"
        jsonl_file = work_dir / f"{dimension}_evidence.jsonl"

        heartbeat = config.heartbeat_callback or _default_heartbeat(dimension, config.source_file_count)

        run_analysis(
            work_dir=config.src,
            prompt=prompt,
            stream_file=stream_file,
            analysis_budget=config.analysis_budget,
            heartbeat_callback=heartbeat,
        )

        if not is_stream_valid(stream_file):
            print(f"  {dimension}: no valid stream, skipping", flush=True)
            continue

        files_read = extract_evidence_from_stream(stream_file, jsonl_file)
        print(f"  {dimension}: {files_read} files read", flush=True)

        ev = parse_jsonl_to_evidence(
            jsonl_file,
            plugin_id=config.plugin_id,
            repository=str(config.src),
            date_str=date_str,
            practices_data=full["practices"],
            source_file_count=config.source_file_count,
            files_read=files_read,
        )
        ev.plugin_name = full["plugin"].get("name", config.plugin_id)
        violations = sum(len(pe.violations) for pe in ev.principles.values())
        compliances = sum(len(pe.compliance) for pe in ev.principles.values())
        print(f"  {dimension}: {violations} violations, {compliances} compliances found", flush=True)
        all_evidence.append(ev)

    return _merge_evidence(all_evidence, config)


def run_per_dimension(config: RunConfig) -> dict[str, Evidence]:
    """Like run(), but returns a dict of {dimension_id: Evidence} without merging."""
    plugin_dir = config.evaluators_dir / config.plugin_id
    if not plugin_dir.exists():
        raise ValueError(f"Plugin directory not found: {plugin_dir}")

    full = load_plugin_full(plugin_dir)
    template = load_template(config.template_path)
    date_str = date.today().isoformat()

    analysis_file = plugin_dir / "knowledge" / "analysis.md"
    analysis_md = analysis_file.read_text() if analysis_file.exists() else ""

    all_dims = [d["id"] for d in full["dimensions"].get("applies", [])]
    if config.dimensions:
        dimensions = [d for d in all_dims if d in config.dimensions]
    else:
        dimensions = all_dims
    work_dir = config.work_dir or config.src

    def _default_heartbeat(dim_name, src_count):
        def _cb(elapsed, progress):
            mins = elapsed // 60
            files = progress.get("files_read", 0)
            evidence = progress.get("evidence", 0)
            if src_count > 0:
                pct = min(round(files / src_count * 100), 100)
                print(f"  {dim_name}: {mins}m elapsed — {files} files read ({pct}%), {evidence} findings", flush=True)
            else:
                print(f"  {dim_name}: {mins}m elapsed — {files} files read, {evidence} findings", flush=True)
        return _cb

    result: dict[str, Evidence] = {}
    total = len(dimensions)

    for idx, dimension in enumerate(dimensions, 1):
        print(f"[{idx}/{total}] Analyzing {dimension}...", flush=True)
        prompt = build_analysis_prompt(
            template,
            plugin_id=config.plugin_id,
            repo_name=str(config.src),
            date_str=date_str,
            dimension=dimension,
            source_file_count=config.source_file_count,
            practices_data=full["practices"],
            dimensions_data=full["dimensions"],
            analysis_md=analysis_md,
            standards_dir=config.standards_dir,
        )

        stream_file = work_dir / f"{dimension}_live.stream"
        jsonl_file = work_dir / f"{dimension}_evidence.jsonl"

        heartbeat = config.heartbeat_callback or _default_heartbeat(dimension, config.source_file_count)

        run_analysis(
            work_dir=config.src,
            prompt=prompt,
            stream_file=stream_file,
            analysis_budget=config.analysis_budget,
            heartbeat_callback=heartbeat,
        )

        if not is_stream_valid(stream_file):
            print(f"  {dimension}: no valid stream, skipping", flush=True)
            continue

        files_read = extract_evidence_from_stream(stream_file, jsonl_file)
        print(f"  {dimension}: {files_read} files read", flush=True)

        ev = parse_jsonl_to_evidence(
            jsonl_file,
            plugin_id=config.plugin_id,
            repository=str(config.src),
            date_str=date_str,
            practices_data=full["practices"],
            source_file_count=config.source_file_count,
            files_read=files_read,
        )
        ev.plugin_name = full["plugin"].get("name", config.plugin_id)

        violations = sum(len(pe.violations) for pe in ev.principles.values())
        compliances = sum(len(pe.compliance) for pe in ev.principles.values())
        print(f"  {dimension}: {violations} violations, {compliances} compliances found", flush=True)
        result[dimension] = ev

    return result


def _merge_evidence(evidence_list: list[Evidence], config: RunConfig) -> Evidence:
    """Merge per-dimension Evidence objects into a single Evidence."""
    merged_principles: dict[str, PrincipleEvidence] = {}
    total_files_read = 0
    total_dismissed = 0

    for ev in evidence_list:
        total_files_read = max(total_files_read, ev.files_read)
        total_dismissed += ev.dismissed_count
        for pid, pe in ev.principles.items():
            if pid in merged_principles:
                existing = merged_principles[pid]
                existing.violations.extend(pe.violations)
                existing.compliance.extend(pe.compliance)
                existing.compute_metrics()
            else:
                merged_principles[pid] = pe

    coverage_pct = (
        round(total_files_read / config.source_file_count * 100, 1)
        if config.source_file_count > 0
        else 0.0
    )

    merged = Evidence(
        repository=str(config.src),
        plugin_id=config.plugin_id,
        date=evidence_list[0].date if evidence_list else "",
        source_file_count=config.source_file_count,
        files_read=total_files_read,
        coverage_pct=coverage_pct,
        principles=merged_principles,
        dismissed_count=total_dismissed,
    )
    if evidence_list:
        merged.plugin_name = evidence_list[0].plugin_name
    return merged


def detect_plugin(src: Path, evaluators_dir: Path) -> str:
    """Auto-detect the best plugin for a repository.

    Uses a two-pass approach:
    1. Check for config files at repo root (strong signal — e.g. pyproject.toml → python)
    2. Fall back to counting source files by extension (weak signal)
    """
    plugins: list[dict] = []
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
        plugins.append(data)

    # Pass 1: config files at repo root
    config_matches: list[tuple[int, str]] = []
    for data in plugins:
        config_files = data.get("detects", {}).get("config_files", [])
        hits = sum(1 for cf in config_files if (src / cf).exists())
        if hits > 0:
            config_matches.append((hits, data.get("id", "")))

    if config_matches:
        config_matches.sort(key=lambda x: x[0], reverse=True)
        return config_matches[0][1]

    # Pass 2: file extension count
    best_id: str | None = None
    best_count = 0
    for data in plugins:
        exts = set(data.get("detects", {}).get("extensions", []))
        if not exts:
            continue
        count = count_source_files(src, exts)
        if count > best_count:
            best_count = count
            best_id = data.get("id", "")

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
    """Full pipeline: run per-dimension → score each → write per-dimension reports.

    Returns dict of {dimension: overall_score_str}.
    """
    from codecompass.v2.engine.scoring import score_evidence
    from codecompass.v2.engine.report import write_dimension_report

    per_dim_evidence = run_per_dimension(config)
    results: dict[str, str] = {}

    for dimension, evidence in per_dim_evidence.items():
        scores = score_evidence(evidence, mode=mode)
        write_dimension_report(evidence, scores, dimension, output_dir)
        overall = scores.get("overall", {})
        if mode == "numerical":
            val = overall.get("weighted_score")
            results[dimension] = f"{val}/10" if val is not None else "N/A"
        else:
            results[dimension] = overall.get("weighted_grade", "N/A")

    return results
