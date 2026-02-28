from codecompass.evaluate.lib.evaluator_generator import build_evaluator, validate_and_build_evaluator


def test_build_evaluator_minimal_shape():
    evaluator = build_evaluator(
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
    assert evaluator["summary"] == "Summary"
    assert evaluator["metadata"]["dimension"] == "MAINTAINABILITY"


def test_validate_and_build_evaluator_reports_errors():
    evaluator, errors = validate_and_build_evaluator(
        discipline="frontend_react",
        dimension="maintainability",
        summary="",
        principle_practice_map=[],
        requirements_coverage=[],
        metadata={"dimension": "X"},
    )
    assert evaluator is not None
    assert errors
