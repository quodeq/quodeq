from pathlib import Path

from codecompass.evaluate.lib.evaluator_generator import validate_and_build_evaluator
from codecompass.evaluate.lib.evaluator_renderer import write_evaluator


def test_generation_smoke(tmp_path: Path):
    evaluator, errors = validate_and_build_evaluator(
        discipline="frontend_react",
        dimension="maintainability",
        summary="Summary",
        principle_practice_map=[],
        requirements_coverage=[],
        metadata={
            "dimension": "MAINTAINABILITY",
            "discipline": "Frontend React",
            "principle_count": 0,
            "practice_count": 0,
            "sources": [],
        },
    )
    assert errors == []
    out_path = tmp_path / "generated" / "evaluators" / "frontend_react" / "maintainability.json"
    write_evaluator(out_path, evaluator)
    assert out_path.is_file()
