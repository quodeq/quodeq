from __future__ import annotations

import json
from pathlib import Path

from codecompass.evaluate.lib.report_json import build_report_json
from codecompass.v2.engine.evidence import Evidence


def build_v2_report(evidence: Evidence, scores: dict) -> dict:
    """Build v2 report: v1 report + v2-specific fields."""
    v1_evidence = evidence.to_v1_evidence_dict()
    base = build_report_json(evidence.plugin_id, v1_evidence, scores)
    base["engine_version"] = "2.0.0"
    base["dismissed_count"] = evidence.dismissed_count
    base["evidence_summary"] = evidence.summary()
    return base


def build_v1_compatible_report(evidence: Evidence, scores: dict) -> dict:
    """Build exact v1 web dashboard format, no v2 fields."""
    v1_evidence = evidence.to_v1_evidence_dict()
    return build_report_json(evidence.plugin_id, v1_evidence, scores)


def write_reports(evidence: Evidence, scores: dict, output_dir: Path) -> None:
    """Write both v2 and v1-compatible report files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    v2_report = build_v2_report(evidence, scores)
    v1_report = build_v1_compatible_report(evidence, scores)

    dim = evidence.plugin_id
    (output_dir / f"{dim}_v2.json").write_text(json.dumps(v2_report, indent=2))
    (output_dir / f"{dim}.json").write_text(json.dumps(v1_report, indent=2))
