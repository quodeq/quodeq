import json
import pytest
from quodeq.adapters.fs.evaluators_repository import FilesystemEvaluatorsRepository


def test_fs_evaluators_repository_reads_evaluator(tmp_path):
    evaluators_dir = tmp_path / "evaluators" / "backend"
    evaluators_dir.mkdir(parents=True)
    (evaluators_dir / "robustness.json").write_text(json.dumps({"metadata": {"dimension": "robustness"}}))

    repo = FilesystemEvaluatorsRepository(root=tmp_path)
    assert repo.list_evaluators("backend") == ["robustness"]
    payload = repo.get_evaluator("backend", "robustness")
    assert payload["metadata"]["dimension"] == "robustness"


def test_fs_evaluators_repository_missing_discipline(tmp_path):
    """list_evaluators raises NotFoundError for non-existent discipline directory."""
    from quodeq.ports.data_errors import NotFoundError
    repo = FilesystemEvaluatorsRepository(root=tmp_path)
    with pytest.raises(NotFoundError):
        repo.list_evaluators("nonexistent")


def test_fs_evaluators_repository_corrupt_json(tmp_path):
    """get_evaluator raises on corrupt JSON file."""
    from quodeq.ports.data_errors import NotFoundError
    evaluators_dir = tmp_path / "evaluators" / "backend"
    evaluators_dir.mkdir(parents=True)
    (evaluators_dir / "broken.json").write_text("{invalid json")

    repo = FilesystemEvaluatorsRepository(root=tmp_path)
    with pytest.raises(NotFoundError, match="Invalid JSON"):
        repo.get_evaluator("backend", "broken")
