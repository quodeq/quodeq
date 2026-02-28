from __future__ import annotations

import json
from pathlib import Path


def write_evaluator(path: Path, evaluator: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evaluator, indent=2))


def extract_analysis_context(evaluator: dict) -> dict:
    """Extract the slim analysis-relevant view of an evaluator JSON.

    Includes: dimension name, per-principle definition, violated_when, practice IDs.
    Strips scoring rubric and other fields not needed during evidence gathering.
    """
    return {
        "dimension": evaluator.get("metadata", {}).get("dimension"),
        "principles": [
            {
                "name": p.get("name"),
                "weight": p.get("weight"),
                "definition": p.get("definition"),
                "violated_when": p.get("violated_when"),
                "practices": [impl.get("id") for impl in p.get("implementing_practices", [])],
            }
            for p in evaluator.get("principles", [])
        ],
    }


def extract_scoring_context(evaluator: dict) -> dict:
    """Extract the slim scoring-relevant view of an evaluator JSON.

    Includes: dimension name, scoring formula, per-principle definition and rubric.
    Strips evidence-gathering fields not needed during scoring.
    """
    return {
        "dimension": evaluator.get("metadata", {}).get("dimension"),
        "scoring_formula": evaluator.get("scoring_formula"),
        "principles": [
            {
                "name": p.get("name"),
                "weight": p.get("weight"),
                "definition": p.get("definition"),
                "scoring_rubric": p.get("scoring_rubric"),
            }
            for p in evaluator.get("principles", [])
        ],
    }
