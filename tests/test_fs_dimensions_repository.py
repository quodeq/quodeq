import json
import pytest
from quodeq.data.fs.dimensions_repository import FilesystemDimensionsRepository


def test_fs_dimensions_repository_reads_dimension(tmp_path):
    dimensions_dir = tmp_path / "dimensions"
    dimensions_dir.mkdir()
    (dimensions_dir / "robustness.json").write_text(json.dumps({"metadata": {"name": "robustness"}}))

    repo = FilesystemDimensionsRepository(root=tmp_path)
    assert repo.list_dimensions() == ["robustness"]
    payload = repo.get_dimension("robustness")
    assert payload["metadata"]["name"] == "robustness"


def test_fs_dimensions_repository_empty_dir(tmp_path):
    dimensions_dir = tmp_path / "dimensions"
    dimensions_dir.mkdir()
    repo = FilesystemDimensionsRepository(root=tmp_path)
    assert repo.list_dimensions() == []


def test_fs_dimensions_repository_get_nonexistent(tmp_path):
    """get_dimension with a non-existent stem raises NotFoundError."""
    from quodeq.data.ports.data_errors import NotFoundError
    dimensions_dir = tmp_path / "dimensions"
    dimensions_dir.mkdir()
    repo = FilesystemDimensionsRepository(root=tmp_path)
    with pytest.raises(NotFoundError, match="nonexistent"):
        repo.get_dimension("nonexistent")


def test_fs_dimensions_repository_missing_dir(tmp_path):
    """Repository with a non-existent root raises NotFoundError on list_dimensions."""
    from quodeq.data.ports.data_errors import NotFoundError
    missing_root = tmp_path / "nonexistent"
    repo = FilesystemDimensionsRepository(root=missing_root)
    with pytest.raises(NotFoundError):
        repo.list_dimensions()
