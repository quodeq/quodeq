from __future__ import annotations

import json
import re
from pathlib import Path

from codecompass.config.generators import run_ai_cli
from codecompass.v2.engine.evidence import Evidence, Judgment, PrincipleEvidence

_PROMPT_PATH = Path(__file__).parent / "prompts" / "judge.md"


def run_judge(
    context: str,
    repository: str,
    plugin_id: str,
    date_str: str,
    practices: dict,
    source_file_count: int,
    files_read: int = 0,
    ai_caller=None,
) -> Evidence:
    """Send context to the LLM judge and parse the JSONL response into Evidence."""
    if ai_caller is None:
        ai_caller = run_ai_cli

    prompt_template = _PROMPT_PATH.read_text()
    prompt = prompt_template.replace("{{CONTEXT}}", context)

    stdout, error = ai_caller(prompt)
    if error:
        raise RuntimeError(f"Judge AI call failed: {error}")

    judgments, dismissed = _parse_judge_output(stdout)

    coverage_pct = (
        round(files_read / source_file_count * 100, 1)
        if source_file_count > 0 and files_read > 0
        else 0.0
    )

    return _assemble_evidence(
        judgments=judgments,
        dismissed_count=dismissed,
        repository=repository,
        plugin_id=plugin_id,
        date_str=date_str,
        practices=practices,
        source_file_count=source_file_count,
        files_read=files_read,
        coverage_pct=coverage_pct,
    )


def _parse_judge_output(raw: str) -> tuple[list[Judgment], int]:
    """Parse JSONL from judge output. Returns (judgments, dismissed_count)."""
    # Strip markdown code fences
    raw = re.sub(r"^\s*```[a-z]*\s*$", "", raw, flags=re.MULTILINE)

    judgments: list[Judgment] = []
    dismissed = 0

    for line in raw.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        practice_id = obj.get("practice_id")
        verdict = obj.get("verdict")
        if not practice_id or not verdict:
            continue

        if verdict == "dismissed":
            dismissed += 1
            continue

        judgments.append(Judgment(
            practice_id=practice_id,
            finding_rule=obj.get("finding_rule", ""),
            file=obj.get("file", ""),
            line=obj.get("line", 0),
            snippet=obj.get("snippet", ""),
            verdict=verdict,
            severity=obj.get("severity", "medium"),
            reason=obj.get("reason", ""),
            dimension=obj.get("dimension", ""),
            cwe=obj.get("cwe"),
            violation_type=obj.get("vt", ""),
        ))

    return judgments, dismissed


def _assemble_evidence(
    judgments: list[Judgment],
    dismissed_count: int,
    repository: str,
    plugin_id: str,
    date_str: str,
    practices: dict,
    source_file_count: int,
    files_read: int,
    coverage_pct: float,
) -> Evidence:
    """Group judgments by practice_id into PrincipleEvidence."""
    # Build practice lookup for display names and dimensions
    practice_lookup: dict[str, dict] = {}
    for p in practices.get("practices", []):
        practice_lookup[p["id"]] = p

    principles: dict[str, PrincipleEvidence] = {}

    for j in judgments:
        if j.practice_id not in principles:
            p_info = practice_lookup.get(j.practice_id, {})
            principles[j.practice_id] = PrincipleEvidence(
                practice_id=j.practice_id,
                display_name=p_info.get("title", j.practice_id),
                dimension=j.dimension or p_info.get("dimension", ""),
                severity=j.severity or p_info.get("severity", "medium"),
            )

        pe = principles[j.practice_id]
        record = {
            "file": j.file,
            "line": j.line,
            "snippet": j.snippet,
            "reason": j.reason,
        }

        if j.verdict == "violation":
            record["severity"] = j.severity
            if j.violation_type:
                record["vt"] = j.violation_type
            pe.violations.append(record)
        elif j.verdict == "compliance":
            pe.compliance.append(record)

    from codecompass.v2.engine.scoring import _scale_multiplier
    scale_mult = _scale_multiplier(source_file_count)

    for pe in principles.values():
        pe.compute_metrics(scale_mult)

    return Evidence(
        repository=repository,
        plugin_id=plugin_id,
        date=date_str,
        source_file_count=source_file_count,
        files_read=files_read,
        coverage_pct=coverage_pct,
        principles=principles,
        dismissed_count=dismissed_count,
    )
