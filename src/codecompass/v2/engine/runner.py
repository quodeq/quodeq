from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from codecompass.config.generators import run_ai_cli
from codecompass.v2.engine.context_builder import build_judge_context
from codecompass.v2.engine.detectors.grep import GrepDetector
from codecompass.v2.engine.evidence import Evidence
from codecompass.v2.engine.finding import Finding
from codecompass.v2.engine.judge import run_judge
from codecompass.v2.engine.plugin_loader import load_plugin_full

_DETECTOR_REGISTRY = {
    "grep": GrepDetector(),
}


@dataclass
class RunConfig:
    src: Path
    plugin_id: str
    evaluators_dir: Path
    standards_dir: Path | None = None
    source_file_count: int = 0
    ai_caller: object = None


def run(config: RunConfig) -> Evidence:
    """Orchestrator: load plugin → detect → build context → judge → Evidence."""
    plugin_dir = config.evaluators_dir / config.plugin_id
    if not plugin_dir.exists():
        raise ValueError(f"Plugin directory not found: {plugin_dir}")

    full = load_plugin_full(plugin_dir)

    findings = _run_detectors(full["detectors"], config.src, plugin_dir)

    # Count files read (files that had at least one finding)
    files_with_findings = {f.file for f in findings if f.file}

    # Load analysis guidance
    analysis_file = plugin_dir / "knowledge" / "analysis.md"
    analysis_md = analysis_file.read_text() if analysis_file.exists() else ""

    context = build_judge_context(
        findings=findings,
        practices=full["practices"],
        analysis_md=analysis_md,
        dimensions_config=full["dimensions"],
        standards_dir=config.standards_dir,
        src_dir=config.src,
    )

    ai_caller = config.ai_caller or run_ai_cli
    files_read = len(files_with_findings) or config.source_file_count

    return run_judge(
        context=context,
        repository=str(config.src),
        plugin_id=config.plugin_id,
        date_str=full["plugin"].get("version", ""),
        practices=full["practices"],
        source_file_count=config.source_file_count,
        files_read=files_read,
        ai_caller=ai_caller,
    )


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

        findings = detector.run(src, config)
        all_findings.extend(findings)

    return all_findings


def run_full(config: RunConfig, output_dir: Path, mode: str = "numerical") -> dict:
    """Full pipeline: run → score → write reports. Returns scores dict."""
    from codecompass.v2.engine.scoring import score_evidence
    from codecompass.v2.engine.report import write_reports

    evidence = run(config)
    scores = score_evidence(evidence, mode=mode)
    write_reports(evidence, scores, output_dir)
    return scores
