import json
from pathlib import Path
from quodeq.analysis.prompts.builder import _load_dimension_data

def test_load_dimension_data_from_compiled(tmp_path):
    compiled = tmp_path / "compiled"
    compiled.mkdir()
    compiled.joinpath("security.json").write_text(json.dumps({"id": "security", "principles": []}))
    result = _load_dimension_data(compiled, "security")
    assert result is not None
    assert result["id"] == "security"

def test_load_dimension_data_fallback_to_evaluators(tmp_path):
    compiled = tmp_path / "compiled"
    compiled.mkdir()
    result = _load_dimension_data(compiled, "nonexistent", evaluators_dir=tmp_path / "evals")
    assert result is None

def test_load_dimension_data_custom_evaluator(tmp_path):
    compiled = tmp_path / "compiled"
    compiled.mkdir()
    evals = tmp_path / "evaluators"
    evals.mkdir()
    evals.joinpath("clean-arch.json").write_text(json.dumps({
        "id": "clean-arch", "principles": [{"name": "SoC", "requirements": []}]
    }))
    result = _load_dimension_data(compiled, "clean-arch", evaluators_dir=evals)
    assert result is not None
    assert result["id"] == "clean-arch"
