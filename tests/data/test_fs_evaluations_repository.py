import json
import pytest
from quodeq.data.fs.evaluations_repository import FilesystemEvaluationsRepository
from quodeq.data.ports.data_errors import NotFoundError


def test_fs_evaluations_repository_reads_report(tmp_path):
    evaluations_dir = tmp_path / "evaluations"
    evaluations_dir.mkdir()
    (evaluations_dir / "run-1.json").write_text(json.dumps({"id": "run-1"}))

    repo = FilesystemEvaluationsRepository(root=tmp_path)
    assert repo.list_reports() == ["run-1"]
    payload = repo.get_report("run-1")
    assert payload["id"] == "run-1"


def test_fs_evaluations_repository_missing_report_raises(tmp_path):
    evaluations_dir = tmp_path / "evaluations"
    evaluations_dir.mkdir()

    repo = FilesystemEvaluationsRepository(root=tmp_path)
    with pytest.raises(NotFoundError):
        repo.get_report("nonexistent")
