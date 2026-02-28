import json
from codecompass.adapters.fs.practices_repository import FilesystemPracticesRepository


def test_fs_practices_repository_reads_practice(tmp_path):
    practices_dir = tmp_path / "practices" / "backend"
    practices_dir.mkdir(parents=True)
    (practices_dir / "solid.json").write_text(json.dumps({"metadata": {"topic": "SOLID"}}))

    repo = FilesystemPracticesRepository(root=tmp_path)
    assert repo.list_topics("backend") == ["solid"]
    payload = repo.get_practice("backend", "solid")
    assert payload["metadata"]["topic"] == "SOLID"
