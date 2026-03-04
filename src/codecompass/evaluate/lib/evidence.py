from __future__ import annotations

import json
import re
from pathlib import Path

from codecompass.evaluate.lib.common import log_error, log_info, log_success, log_warning

DEFAULT_WEIGHT = "Medium (x2)"


def _read_jsonl_findings(jsonl_file: str) -> tuple[dict, int, int]:
    """Read a JSONL file and group valid findings by principle key.

    Returns a tuple of (principles, accepted_count, rejected_count).
    Only entries with a principle key ('p') and a recognised type ('t') are kept.
    """
    principles: dict = {}
    accepted = 0
    rejected = 0

    with open(jsonl_file) as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                rejected += 1
                continue

            p_key = obj.get("p")
            entry_type = obj.get("t")
            if not p_key or entry_type not in ("violation", "compliance"):
                rejected += 1
                continue

            accepted += 1

            if p_key not in principles:
                principles[p_key] = {
                    "display_name": obj.get("d", p_key),
                    "weight": obj.get("w", DEFAULT_WEIGHT),
                    "violations": [],
                    "compliance": [],
                }

            bucket = principles[p_key]

            raw_snippet = obj.get("snippet", "")
            snippet = raw_snippet.split("\n")[0].strip() if raw_snippet else ""

            record: dict = {
                "file": obj.get("file", ""),
                "line": obj.get("line", 0),
                "snippet": snippet,
                "reason": obj.get("reason", ""),
            }
            if entry_type == "violation":
                record["severity"] = obj.get("severity", "minor")
                vt = obj.get("vt")
                if vt:
                    record["vt"] = vt
                bucket["violations"].append(record)
            else:
                bucket["compliance"].append(record)

    return principles, accepted, rejected


def _remove_duplicates(principles: dict) -> int:
    """Drop duplicate findings that share the same (file, line) pair.

    Returns the number of entries removed.
    """
    dropped = 0
    for bucket in principles.values():
        for list_key in ("violations", "compliance"):
            seen: set = set()
            unique = []
            for item in bucket[list_key]:
                coord = (item.get("file", ""), item.get("line", 0))
                if coord not in seen:
                    seen.add(coord)
                    unique.append(item)
                else:
                    dropped += 1
            bucket[list_key] = unique
    return dropped


def _compute_principle_metrics(principles: dict, scale_multiplier: int = 1) -> None:
    """Attach a metrics block to each principle bucket (mutates in-place)."""
    high_threshold = 10 * scale_multiplier
    medium_threshold = 5 * scale_multiplier

    for bucket in principles.values():
        n_violations = len(bucket["violations"])
        n_compliance = len(bucket["compliance"])
        total = n_violations + n_compliance
        pct = round(n_compliance / total * 100, 1) if total > 0 else 0.0

        if total >= high_threshold:
            confidence = "high"
        elif total >= medium_threshold:
            confidence = "medium"
        else:
            confidence = "low"

        bucket["metrics"] = {
            "total_instances": total,
            "compliant": n_compliance,
            "violating": n_violations,
            "compliance_percentage": pct,
            "confidence_level": confidence,
            "is_balanced": n_violations > 0 and n_compliance > 0,
        }


def _build_summary(principles: dict) -> dict:
    """Return aggregate statistics across all principles."""
    total = sum(b["metrics"]["total_instances"] for b in principles.values())
    low_conf = [k for k, b in principles.items() if b["metrics"]["confidence_level"] == "low"]
    unbalanced = [k for k, b in principles.items() if not b["metrics"]["is_balanced"]]

    return {
        "total_findings": total,
        "principles_count": len(principles),
        "low_confidence_principles": low_conf,
        "unbalanced_principles": unbalanced,
        "overall_confidence": (
            "low" if len(low_conf) > len(principles) / 2
            else "medium" if low_conf
            else "high"
        ),
    }


def assemble_evidence_from_jsonl(
    jsonl_file: str,
    output_file: str,
    repo_name: str,
    discipline: str,
    date_str: str,
    source_file_count: int = 0,
    files_read: int = 0,
    analysis_hash: str = "",
    scoring_hash: str = "",
    mapping_hash: str = "",
    codecompass_version: str = "",
) -> bool:
    """Convert a JSONL evidence file into the monolithic evidence JSON format.

    Returns True on success, False when the input is empty or contains no
    recognised findings.
    """
    path = Path(jsonl_file)
    if not path.exists() or path.stat().st_size == 0:
        log_error(f"JSONL file is empty or missing: {jsonl_file}")
        return False

    principles, accepted, rejected = _read_jsonl_findings(jsonl_file)
    dropped = _remove_duplicates(principles)
    from codecompass.evaluate.lib.scale import scale_multiplier
    scale_mult = scale_multiplier(source_file_count)
    _compute_principle_metrics(principles, scale_multiplier=scale_mult)

    if not principles:
        log_error("No valid findings parsed from JSONL")
        return False

    coverage_pct = (
        round(files_read / source_file_count * 100, 1)
        if source_file_count > 0 and files_read > 0
        else 0.0
    )
    result = {
        "repository": repo_name,
        "discipline": discipline,
        "date": date_str,
        "source_file_count": source_file_count,
        "files_read": files_read,
        "coverage_pct": coverage_pct,
        "meta": {
            "analysis_prompt_version": analysis_hash,
            "scoring_prompt_version": scoring_hash,
            "mapping_file_hash": mapping_hash,
            "codecompass_version": codecompass_version,
        },
        "principles": principles,
        "evidence_summary": _build_summary(principles),
    }

    with open(output_file, "w") as fh:
        json.dump(result, fh, indent=2)

    extras = []
    if rejected:
        extras.append(f"{rejected} skipped")
    if dropped:
        extras.append(f"{dropped} duplicates removed")
    suffix = f"  ({', '.join(extras)})" if extras else ""
    log_success(f"{accepted} findings across {len(principles)} principles{suffix}")
    return True


def _strip_fences_and_extract_json(content: str) -> str | None:
    """Pull the outermost JSON object from text that may have markdown fences."""
    content = re.sub(r"^\s*```[a-z]*\s*$", "", content, flags=re.MULTILINE)
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return content[start : end + 1]


def _check_evidence_structure(data: dict) -> tuple[bool, str | None]:
    """Return (ok, error_message) after checking minimum required structure."""
    if "principles" not in data:
        return False, 'Missing "principles" key in evidence JSON'
    if not data["principles"]:
        return False, '"principles" object is empty'
    return True, None


def validate_evidence_json(file: str) -> bool:
    """Parse, validate, and normalise an evidence JSON file in-place.

    Returns True when the file is valid, False otherwise.
    """
    path = Path(file)
    if not path.exists() or path.stat().st_size == 0:
        log_error(f"Evidence file is empty or missing: {file}")
        return False

    content = path.read_text()
    json_str = _strip_fences_and_extract_json(content)
    if json_str is None:
        log_error("No JSON object found in output")
        return False

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        log_error(f"Invalid JSON: {exc}")
        return False

    ok, error_msg = _check_evidence_structure(data)
    if not ok:
        log_error(f"Evidence validation: {error_msg}")
        return False

    path.write_text(json.dumps(data, indent=2))
    return True


def build_evidence_file(
    jsonl_file: str,
    evidence_file: str,
    project_name: str,
    discipline: str,
    today: str,
    source_file_count: int,
    files_read: int = 0,
    analysis_hash: str = "",
    scoring_hash: str = "",
    mapping_hash: str = "",
    codecompass_version: str = "",
    dimension_tag: str = "",
) -> bool:
    """Assemble JSONL into evidence JSON, validate it, and write a fallback if needed.

    Returns True when valid evidence is available, False otherwise.
    """
    has_evidence = assemble_evidence_from_jsonl(
        jsonl_file, evidence_file, project_name, discipline, today,
        source_file_count, files_read, analysis_hash, scoring_hash, mapping_hash, codecompass_version,
    )
    if not has_evidence:
        log_warning("No valid evidence found — scoring will note insufficient evidence")

    if has_evidence:
        if not validate_evidence_json(evidence_file):
            log_error("Evidence validation failed")
            has_evidence = False

    if not has_evidence:
        log_warning("Creating minimal evidence — scores will reflect insufficient data")
        minimal = {
            "repository": project_name,
            "discipline": discipline,
            "date": today,
            "source_file_count": source_file_count,
            "files_read": files_read,
            "coverage_pct": 0.0,
            "meta": {
                "analysis_prompt_version": analysis_hash,
                "scoring_prompt_version": scoring_hash,
                "mapping_file_hash": mapping_hash,
                "codecompass_version": codecompass_version,
            },
            "principles": {},
        }
        Path(evidence_file).write_text(json.dumps(minimal))

    return has_evidence
