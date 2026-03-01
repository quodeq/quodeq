from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from codecompass.evaluate.lib.analysis import (
    is_stream_valid,
    dump_debug_sample,
    extract_jsonl_evidence,
    run_analysis_phase,
    run_scoring_phase,
)
from codecompass.evaluate.lib.common import log_error, log_info, log_step, log_warning
from codecompass.evaluate.lib.evidence import build_evidence_file
from codecompass.evaluate.lib.evaluator_renderer import (
    extract_analysis_context,
    extract_scoring_context,
)
from codecompass.evaluate.lib.prompts import build_analysis_jsonl_prompt, build_scoring_prompt, detect_scoring_mode
from codecompass.evaluate.lib.report_json import write_report_json
from codecompass.evaluate.lib.scoring import run_scoring


def compute_prompt_hash(content: str) -> str:
    """Compute a short MD5 hash of a string (first 8 hex chars)."""
    return hashlib.md5(content.encode()).hexdigest()[:8]


def run_two_phase_dimension(
    work_dir: str,
    dimension: str,
    discipline: str,
    project_name: str,
    today: str,
    evidence_file: str,
    eval_file: str,
    analysis_template: str,
    scoring_template: str,
    analysis_standards: str = "",
    scoring_standards: str = "",
    source_file_count: int = 0,
    analysis_hash: str = "",
    scoring_hash: str = "",
    mapping_hash: str = "",
    codecompass_version: str = "",
    prescan_metrics: str = "",
    prescan_guidance: str = "",
    evidence_only: bool = False,
    numerical: bool = False,
    mapping_file: str | None = None,
) -> bool:
    """Orchestrate the two-phase evaluation for a single dimension.

    Phase 1: Analysis — AI gathers JSONL evidence by reading the repo.
    Phase 2: Scoring — AI scores the assembled evidence against the rubric.

    Returns True on success, False on failure.
    """
    dimension_tag = f"[{dimension}]"

    # Ensure output directories exist
    Path(evidence_file).parent.mkdir(parents=True, exist_ok=True)
    Path(eval_file).parent.mkdir(parents=True, exist_ok=True)

    # --- Build analysis prompt ---
    analysis_prompt = build_analysis_jsonl_prompt(
        template=analysis_template,
        discipline=discipline,
        project_name=project_name,
        today=today,
        standards_content=analysis_standards,
        source_file_count=source_file_count,
        analysis_hash=analysis_hash,
        prescan_metrics=prescan_metrics,
        prescan_guidance=prescan_guidance,
    )

    log_step("Gathering evidence")

    # --- Phase 1: Analysis ---
    with (
        tempfile.NamedTemporaryFile(mode="w", suffix=".stream", delete=False) as sf,
        tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as jf,
    ):
        stream_file = sf.name
        jsonl_file = jf.name

    try:
        run_analysis_phase(work_dir, dimension, analysis_prompt, stream_file, dimension_tag)
        extract_jsonl_evidence(stream_file, jsonl_file, dimension)

        # Debug sample when stream had content but no evidence was extracted
        stream_path = Path(stream_file)
        jsonl_path = Path(jsonl_file)
        if (
            stream_path.exists()
            and stream_path.stat().st_size > 0
            and (not jsonl_path.exists() or jsonl_path.stat().st_size == 0)
        ):
            debug_dir = Path(evidence_file).parent
            debug_stream = str(debug_dir / f"{dimension}_debug_stream.json")
            dump_debug_sample(stream_file, debug_stream, dimension_tag)

        stream_ok = is_stream_valid(stream_file)
        Path(stream_file).unlink(missing_ok=True)
        Path(stream_file + ".err").unlink(missing_ok=True)

        if not stream_ok:
            if jsonl_path.exists() and jsonl_path.stat().st_size > 0:
                log_warning("Analysis budget reached — proceeding with partial evidence")
            else:
                log_error(f"{dimension_tag} Analysis produced no output")
                return False

        # --- Assemble + validate evidence ---
        has_evidence = build_evidence_file(
            jsonl_file=jsonl_file,
            evidence_file=evidence_file,
            project_name=project_name,
            discipline=discipline,
            today=today,
            source_file_count=source_file_count,
            analysis_hash=analysis_hash,
            scoring_hash=scoring_hash,
            mapping_hash=mapping_hash,
            codecompass_version=codecompass_version,
            dimension_tag=dimension_tag,
        )
    finally:
        Path(jsonl_file).unlink(missing_ok=True)

    if evidence_only:
        return has_evidence

    # --- Compute deterministic scores ---
    scoring_mode = "numerical" if numerical else detect_scoring_mode(scoring_template)
    scores_file = str(
        Path(evidence_file).with_name(
            Path(evidence_file).stem.replace("_evidence", "_scores") + ".json"
        )
    )
    if mapping_file and Path(mapping_file).exists() and has_evidence:
        try:
            with open(evidence_file) as f:
                evidence_data = json.load(f)
            with open(mapping_file) as f:
                mapping_data = json.load(f)
            scores_data = run_scoring(evidence_data, mapping_data, scoring_mode)
            with open(scores_file, "w") as f:
                json.dump(scores_data, f, indent=2, sort_keys=True)
        except Exception as exc:
            log_warning(f"Score computation failed: {exc}")

    # --- Phase 2: Scoring ---
    evidence_content = Path(evidence_file).read_text() if Path(evidence_file).exists() else ""
    loaded_scores = Path(scores_file).read_text() if Path(scores_file).exists() else ""
    scoring_prompt = build_scoring_prompt(
        template=scoring_template,
        discipline=discipline,
        project_name=project_name,
        today=today,
        eval_file=eval_file,
        standards_content=scoring_standards,
        dimension=dimension,
        evidence_content=evidence_content,
        scores_content=loaded_scores,
        analysis_hash=analysis_hash,
        scoring_hash=scoring_hash,
        mapping_hash=mapping_hash,
        codecompass_version=codecompass_version,
        scoring_mode=scoring_mode,
    )

    ok = run_scoring_phase(work_dir, dimension, scoring_prompt, eval_file, dimension_tag, has_evidence)
    if not ok:
        return False

    # --- Generate dashboard JSON (non-fatal) ---
    json_out = str(Path(eval_file).parent / f"{dimension}.json")
    try:
        write_report_json(
            evidence_file=evidence_file,
            output_file=json_out,
            scores_file=scores_file if Path(scores_file).exists() else None,
        )
    except Exception as exc:
        log_warning(f"JSON report generation failed — dashboard will fall back to .md: {exc}")

    return True
