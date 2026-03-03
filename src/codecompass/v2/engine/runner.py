from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codecompass.config.generators import run_ai_cli
from codecompass.v2.engine.context_builder import build_judge_context
from codecompass.v2.engine.detectors.grep import GrepDetector
from codecompass.v2.engine.detectors.tool import ToolDetector, register_parser
from codecompass.v2.engine.detectors.parsers.eslint import parse_eslint_output
from codecompass.v2.engine.evidence import Evidence, Judgment
from codecompass.v2.engine.file_sampler import sample_files
from codecompass.v2.engine.finding import Finding
from codecompass.v2.engine.judge import run_judge, _parse_judge_output, _assemble_evidence
from codecompass.v2.engine.plugin_loader import load_plugin_full
from codecompass.v2.engine.reviewer import run_code_review


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_DETECTOR_REGISTRY = {
    "grep": GrepDetector(),
    "tool": ToolDetector(),
}

# Register built-in parsers
register_parser("eslint", parse_eslint_output)


@dataclass
class RunConfig:
    src: Path
    plugin_id: str
    evaluators_dir: Path
    standards_dir: Path | None = None
    source_file_count: int = 0
    ai_caller: object = None
    dimensions: list[str] | None = None


def run(config: RunConfig) -> Evidence:
    """Orchestrator: load plugin → detect → judge (Pass 1) → review (Pass 2) → Evidence."""
    plugin_dir = config.evaluators_dir / config.plugin_id
    if not plugin_dir.exists():
        raise ValueError(f"Plugin directory not found: {plugin_dir}")

    full = load_plugin_full(plugin_dir)

    # Filter dimensions and practices if -d was specified
    if config.dimensions:
        dim_set = set(config.dimensions)
        full["dimensions"]["applies"] = [
            d for d in full["dimensions"]["applies"]
            if d["id"] in dim_set
        ]
        if "practices" in full["practices"]:
            full["practices"]["practices"] = [
                p for p in full["practices"]["practices"]
                if p.get("dimension") in dim_set
            ]

    findings = _run_detectors(full["detectors"], config.src, plugin_dir)

    # Filter findings to requested dimensions so the judge only sees relevant ones
    if config.dimensions:
        dim_set_lower = {d.lower() for d in config.dimensions}
        findings = [f for f in findings if f.dimension.lower() in dim_set_lower]

    # Count files read (files that had at least one finding)
    files_with_findings = {f.file for f in findings if f.file}

    # Load analysis guidance
    analysis_file = plugin_dir / "knowledge" / "analysis.md"
    analysis_md = analysis_file.read_text() if analysis_file.exists() else ""

    ai_caller = config.ai_caller or run_ai_cli

    # ── Pass 1: Judge triages detector findings ──────────────────────
    context = build_judge_context(
        findings=findings,
        practices=full["practices"],
        analysis_md=analysis_md,
        dimensions_config=full["dimensions"],
        standards_dir=config.standards_dir,
        src_dir=config.src,
    )

    judge_judgments, judge_dismissed = _run_judge_pass(context, ai_caller)

    # ── Pass 2: LLM reads actual source files ────────────────────────
    extensions = set(full["plugin"].get("detects", {}).get("extensions", []))
    sampled = sample_files(config.src, findings, extensions)

    review_judgments, review_dismissed = run_code_review(
        sampled_files=sampled,
        practices=full["practices"],
        analysis_md=analysis_md,
        dimensions_config=full["dimensions"],
        ai_caller=ai_caller,
    )

    # ── Merge and deduplicate ────────────────────────────────────────
    all_judgments = _deduplicate(judge_judgments + review_judgments)
    total_dismissed = judge_dismissed + review_dismissed

    # Count files read: union of detector-hit files and sampled files
    sampled_files_set = {sf.path for sf in sampled}
    all_files_read = files_with_findings | sampled_files_set
    files_read = len(all_files_read) or config.source_file_count

    coverage_pct = (
        round(files_read / config.source_file_count * 100, 1)
        if config.source_file_count > 0 and files_read > 0
        else 0.0
    )

    return _assemble_evidence(
        judgments=all_judgments,
        dismissed_count=total_dismissed,
        repository=str(config.src),
        plugin_id=config.plugin_id,
        date_str=_now_iso(),
        practices=full["practices"],
        source_file_count=config.source_file_count,
        files_read=files_read,
        coverage_pct=coverage_pct,
    )


def _run_judge_pass(context: str, ai_caller) -> tuple[list[Judgment], int]:
    """Run Pass 1: send context to judge LLM and parse JSONL."""
    from codecompass.v2.engine.judge import _PROMPT_PATH

    prompt_template = _PROMPT_PATH.read_text()
    prompt = prompt_template.replace("{{CONTEXT}}", context)

    stdout, error = ai_caller(prompt)
    if error:
        raise RuntimeError(f"Judge AI call failed: {error}")

    return _parse_judge_output(stdout)


def _deduplicate(judgments: list[Judgment]) -> list[Judgment]:
    """Deduplicate judgments by (file, line, practice_id). Keep longer reason."""
    seen: dict[tuple[str, int, str], Judgment] = {}
    for j in judgments:
        key = (j.file, j.line, j.practice_id)
        if key in seen:
            existing = seen[key]
            if len(j.reason) > len(existing.reason):
                seen[key] = j
        else:
            seen[key] = j
    return list(seen.values())


def _run_detectors(detectors_config: list, src: Path, plugin_dir: Path) -> list[Finding]:
    """Run all configured detectors and collect findings."""
    all_findings: list[Finding] = []

    for det_config in detectors_config:
        det_type = det_config.get("type")
        detector = _DETECTOR_REGISTRY.get(det_type)
        if not detector:
            continue

        config = {}
        if det_type == "grep":
            rules_file = det_config.get("rules", "scan_rules.ini")
            config["rules_file"] = str(plugin_dir / rules_file)
        elif det_type == "tool":
            config["tool"] = det_config.get("tool", "")
            config["command"] = det_config.get("command", "")
            config["optional"] = det_config.get("optional", False)
            config["timeout"] = det_config.get("timeout", 60)

        findings = detector.run(src, config)
        all_findings.extend(findings)

    return all_findings


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
    """Full pipeline: run → score → write reports. Returns scores dict."""
    from codecompass.v2.engine.scoring import score_evidence
    from codecompass.v2.engine.report import write_reports

    evidence = run(config)
    scores = score_evidence(evidence, mode=mode)
    write_reports(evidence, scores, output_dir, dimensions=config.dimensions)
    return scores
