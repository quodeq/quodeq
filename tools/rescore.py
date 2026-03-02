#!/usr/bin/env python3
"""Re-apply deterministic scoring to all existing evidence files.

Usage:
    python3 tools/rescore.py [evaluations_dir] [project]

Defaults:
    evaluations_dir = evaluations/
    project         = codecompass
"""
import json
import sys
from pathlib import Path

# Allow running from repo root without installing the package
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "src"))

from codecompass.evaluate.lib.scoring import run_scoring
from codecompass.evaluate.lib.report_json import write_report_json

SCORING_MODE_BY_HASH = {
    "6fee1ee3": "numerical",
    "33f4ef56": "non-numerical",
}
DEFAULT_SCORING_MODE = "numerical"


def detect_mode_from_evidence(evidence: dict) -> str:
    h = evidence.get("meta", {}).get("scoring_prompt_version", "")
    return SCORING_MODE_BY_HASH.get(h, DEFAULT_SCORING_MODE)


def rescore_evidence_file(evidence_path: Path, evaluators_root: Path) -> bool:
    evidence = json.loads(evidence_path.read_text())
    discipline = evidence.get("discipline", "")
    dimension = evidence_path.stem.replace("_evidence", "")
    mapping_path = evaluators_root / discipline / f"{dimension}.json"

    if not mapping_path.exists():
        print(f"  SKIP  mapping not found: {mapping_path}")
        return False

    mapping = json.loads(mapping_path.read_text())
    mode = detect_mode_from_evidence(evidence)
    scores = run_scoring(evidence, mapping, mode)

    scores_path = evidence_path.with_name(f"{dimension}_scores.json")
    scores_path.write_text(json.dumps(scores, indent=2, sort_keys=True))

    # evaluation/{dimension}.json lives one level up, in sibling "evaluation" dir
    eval_dir = evidence_path.parent.parent / "evaluation"
    eval_dir.mkdir(exist_ok=True)
    output_path = eval_dir / f"{dimension}.json"

    write_report_json(
        evidence_file=str(evidence_path),
        output_file=str(output_path),
        scores_file=str(scores_path),
    )

    overall = scores.get("overall", {})
    score = overall.get("score", "?")
    grade = overall.get("grade", "?")
    tier = scores.get("scale", {}).get("tier", "?")
    print(f"  OK    {dimension:<20}  score={score}  grade={grade}  tier={tier}")
    return True


def main():
    evals_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else repo_root / "evaluations"
    project = sys.argv[2] if len(sys.argv) > 2 else "codecompass"
    project_dir = evals_dir / project

    if not project_dir.exists():
        print(f"Project dir not found: {project_dir}")
        sys.exit(1)

    evaluators_root = repo_root / "v1" / "evaluators"
    evidence_files = sorted(project_dir.glob("*/evidence/*_evidence.json"))

    print(f"Found {len(evidence_files)} evidence files in {project_dir}\n")
    ok = fail = 0
    for ef in evidence_files:
        run_id = ef.parents[1].name
        print(f"[{run_id}]")
        if rescore_evidence_file(ef, evaluators_root):
            ok += 1
        else:
            fail += 1

    print(f"\nDone — {ok} rescored, {fail} skipped/failed")


if __name__ == "__main__":
    main()
