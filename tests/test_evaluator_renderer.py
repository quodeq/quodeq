from pathlib import Path
import json

from codecompass.evaluate.lib.evaluator_renderer import write_evaluator


def test_write_evaluator_creates_file(tmp_path: Path):
    evaluator = {
        "metadata": {
            "dimension": "MAINTAINABILITY",
            "discipline": "Frontend React",
            "principle_count": 0,
            "practice_count": 0,
            "sources": [],
        },
        "summary": "Summary",
        "principle_practice_map": [],
        "requirements_coverage": [],
    }
    out_path = tmp_path / "generated" / "evaluators" / "frontend_react" / "maintainability.json"
    write_evaluator(out_path, evaluator)
    assert json.loads(out_path.read_text())["summary"] == "Summary"
