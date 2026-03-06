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


def run(config: RunConfig) -> Evidence:
    """Orchestrate: load plugin → per-dimension AI analysis → merged Evidence."""
    plugin_dir = config.evaluators_dir / config.plugin_id
    if not plugin_dir.exists():
        raise ValueError(f"Plugin directory not found: {plugin_dir}")

    full = load_plugin_full(plugin_dir)
    template = load_template(config.template_path)

    analysis_file = plugin_dir / "knowledge" / "analysis.md"
    analysis_md = analysis_file.read_text() if analysis_file.exists() else ""

    dimensions = [d["id"] for d in full["dimensions"].get("applies", [])]
    work_dir = config.work_dir or config.src

    all_evidence: list[Evidence] = []

    for dimension in dimensions:
        prompt = build_analysis_prompt(
            template,
            plugin_id=config.plugin_id,
            repo_name=str(config.src),
            date_str=full["plugin"].get("version", ""),
            dimension=dimension,
            source_file_count=config.source_file_count,
            practices_data=full["practices"],
            dimensions_data=full["dimensions"],
            analysis_md=analysis_md,
            standards_dir=config.standards_dir,
        )

        stream_file = work_dir / f"{dimension}_live.stream"
        jsonl_file = work_dir / f"{dimension}_evidence.jsonl"

        run_analysis(
            work_dir=config.src,
            prompt=prompt,
            stream_file=stream_file,
            analysis_budget=config.analysis_budget,
            heartbeat_callback=config.heartbeat_callback,
        )

        if not is_stream_valid(stream_file):
            continue

        files_read = extract_evidence_from_stream(stream_file, jsonl_file)

        ev = parse_jsonl_to_evidence(
            jsonl_file,
            plugin_id=config.plugin_id,
            repository=str(config.src),
            date_str=full["plugin"].get("version", ""),
            practices_data=full["practices"],
            source_file_count=config.source_file_count,
            files_read=files_read,
        )
        all_evidence.append(ev)

    return _merge_evidence(all_evidence, config)


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

    return Evidence(
        repository=str(config.src),
        plugin_id=config.plugin_id,
        date=evidence_list[0].date if evidence_list else "",
        source_file_count=config.source_file_count,
        files_read=total_files_read,
        coverage_pct=coverage_pct,
        principles=merged_principles,
        dismissed_count=total_dismissed,
    )


def detect_plugin(src: Path, evaluators_dir: Path) -> str:
    """Auto-detect the best plugin for a repository by counting extension matches."""
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
    """Full pipeline: run → score → write reports. Returns scores dict."""
    from codecompass.v2.engine.scoring import score_evidence
    from codecompass.v2.engine.report import write_reports

    evidence = run(config)
    scores = score_evidence(evidence, mode=mode)
    write_reports(evidence, scores, output_dir)
    return scores
