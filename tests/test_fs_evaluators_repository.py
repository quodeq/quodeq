import json
from codecompass.adapters.fs.evaluators_repository import FilesystemEvaluatorsRepository


def test_fs_evaluators_repository_reads_evaluator(tmp_path):
    evaluators_dir = tmp_path / "evaluators" / "backend"
    evaluators_dir.mkdir(parents=True)
    (evaluators_dir / "robustness.json").write_text(json.dumps({"metadata": {"dimension": "robustness"}}))

    repo = FilesystemEvaluatorsRepository(root=tmp_path)
    assert repo.list_evaluators("backend") == ["robustness"]
    payload = repo.get_evaluator("backend", "robustness")
    assert payload["metadata"]["dimension"] == "robustness"
