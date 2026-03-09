import json
from quodeq.adapters.fs.dimensions_repository import FilesystemDimensionsRepository


def test_fs_dimensions_repository_reads_dimension(tmp_path):
    dimensions_dir = tmp_path / "dimensions"
    dimensions_dir.mkdir()
    (dimensions_dir / "robustness.json").write_text(json.dumps({"metadata": {"name": "robustness"}}))

    repo = FilesystemDimensionsRepository(root=tmp_path)
    assert repo.list_dimensions() == ["robustness"]
    payload = repo.get_dimension("robustness")
    assert payload["metadata"]["name"] == "robustness"
