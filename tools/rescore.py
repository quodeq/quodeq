#!/usr/bin/env python3
"""Re-apply deterministic scoring to all existing evidence files.

Usage:
    python3 tools/rescore.py [evaluations_dir] [project]
    python3 tools/rescore.py --dry-run                      # preview changes
    python3 tools/rescore.py --apply                        # write changes (default is dry-run)

Defaults:
    evaluations_dir = evaluations/
    project         = quodeq
"""
import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root without installing the package.
# This mirrors the same pattern used by tools/compile_standards.py.
# When invoked via `uv run python tools/rescore.py` the venv handles
# discovery automatically; the insert is only needed for bare `python3`
# invocations outside the project venv.
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "src"))

from quodeq.evaluate.lib.scoring import run_scoring
from quodeq.evaluate.lib.report_json import write_report_json

# Content hashes that identify prompt versions — used to select the correct
# scoring mode for evidence produced by different prompt revisions.
_SCORING_PROMPT_V1_HASH = "6fee1ee3"  # scoring prompt v1 (numerical deductions)
_SCORING_PROMPT_V2_HASH = "33f4ef56"  # scoring prompt v2 (grade-ladder drops)

SCORING_MODE_BY_HASH = {
    _SCORING_PROMPT_V1_HASH: "numerical",
    _SCORING_PROMPT_V2_HASH: "non-numerical",
}
DEFAULT_SCORING_MODE = "numerical"
_EVIDENCE_STEM_SUFFIX = "_evidence"


def detect_mode_from_evidence(evidence: dict) -> str:
    """Return the scoring mode ('numerical' or 'non-numerical') for *evidence*."""
    h = evidence.get("meta", {}).get("scoring_prompt_version", "")
    return SCORING_MODE_BY_HASH.get(h, DEFAULT_SCORING_MODE)


def _write_scores_and_report(evidence_path: Path, dimension: str, scores: dict) -> bool:
    """Write scores JSON and evaluation report to disk. Returns True on success."""
    overall = scores.get("overall", {})
    score = overall.get("score", "?")
    grade = overall.get("grade", "?")
    tier = scores.get("scale", {}).get("tier", "?")

    scores_path = evidence_path.with_name(f"{dimension}_scores.json")
    try:
        scores_path.write_text(json.dumps(scores, indent=2, sort_keys=True))
    except OSError as exc:
        print(f"  ERROR writing {scores_path}: {exc}")
        return False

    # evaluation/{dimension}.json lives one level up, in sibling "evaluation" dir
    eval_dir = evidence_path.parent.parent / "evaluation"
    eval_dir.mkdir(exist_ok=True)
    output_path = eval_dir / f"{dimension}.json"

    try:
        write_report_json(
            evidence_file=str(evidence_path),
            output_file=str(output_path),
            scores_file=str(scores_path),
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"  ERROR writing report {output_path}: {exc}")
        return False

    print(f"  OK    {dimension:<20}  score={score}  grade={grade}  tier={tier}")
    return True


def rescore_evidence_file(evidence_path: Path, evaluators_root: Path, *, dry_run: bool = False) -> bool:
    """Re-score a single evidence file and write updated scores/report.

    Returns True on success (or dry-run preview), False if the file is
    unreadable or the mapping is missing.
    """
    try:
        evidence = json.loads(evidence_path.read_text())
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"  SKIP  cannot read {evidence_path}: {exc}")
        return False
    discipline = evidence.get("discipline", "")
    dimension = evidence_path.stem.replace(_EVIDENCE_STEM_SUFFIX, "")
    mapping_path = evaluators_root / discipline / f"{dimension}.json"

    if not mapping_path.exists():
        print(f"  SKIP  mapping not found: {mapping_path}")
        return False

    mode = detect_mode_from_evidence(evidence)
    try:
        scores = run_scoring(evidence, mode)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        print(f"  SKIP  scoring failed for {evidence_path}: {exc}")
        return False

    if dry_run:
        overall = scores.get("overall", {})
        score = overall.get("score", "?")
        grade = overall.get("grade", "?")
        tier = scores.get("scale", {}).get("tier", "?")
        print(f"  DRY   {dimension:<20}  score={score}  grade={grade}  tier={tier}")
        return True

    return _write_scores_and_report(evidence_path, dimension, scores)


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Re-apply deterministic scoring to all existing evidence files.",
    )
    parser.add_argument(
        "evaluations_dir", nargs="?", default=None,
        help="Evaluations root directory (default: evaluations/)",
    )
    parser.add_argument(
        "project", nargs="?", default="quodeq",
        help="Project name (default: quodeq)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Preview what would change without writing (default)",
    )
    group.add_argument(
        "--apply", action="store_true", dest="apply_",
        help="Write changes",
    )
    return parser


def main():
    args = _build_parser().parse_args()

    dry_run = not args.apply_
    evals_dir = Path(args.evaluations_dir) if args.evaluations_dir else repo_root / "evaluations"
    project_dir = evals_dir / args.project

    if not project_dir.exists():
        print(f"Project dir not found: {project_dir}")
        sys.exit(1)

    _EVALUATORS_DIR = "evaluators"
    evaluators_root = repo_root / _EVALUATORS_DIR
    evidence_files = sorted(project_dir.glob("*/evidence/*_evidence.json"))

    mode_label = "DRY-RUN" if dry_run else "APPLY"
    print(f"Found {len(evidence_files)} evidence files in {project_dir}  [{mode_label}]\n")
    ok = fail = 0
    for ef in evidence_files:
        run_id = ef.parents[1].name
        print(f"[{run_id}]")
        if rescore_evidence_file(ef, evaluators_root, dry_run=dry_run):
            ok += 1
        else:
            fail += 1

    print(f"\nDone — {ok} rescored, {fail} skipped/failed")
    if dry_run and ok:
        print("Run with --apply to write changes.")


if __name__ == "__main__":
    main()
