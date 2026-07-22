"""_create_project must fail cleanly when the metadata write fails (REL-047)."""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.data.fs._models import ProjectIdentity
from quodeq.data.fs._resolution import _REPO_INFO_FILENAME, _create_project


def _identity() -> ProjectIdentity:
    return ProjectIdentity(project_name="proj", repo_path="/tmp/proj")


def test_metadata_write_failure_propagates_and_skips_index(tmp_path, monkeypatch):
    saved: list[dict] = []

    def load_fn(reports_dir: Path) -> dict:
        return {}

    def save_fn(reports_dir: Path, index: dict) -> None:
        saved.append(dict(index))

    original_write_text = Path.write_text

    def failing_write_text(self, *args, **kwargs):
        if self.name == _REPO_INFO_FILENAME:
            raise OSError("disk full")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing_write_text)

    with pytest.raises(OSError):
        _create_project(tmp_path, _identity(), load_fn, save_fn)

    # The identity-to-project index must not record the broken project.
    assert saved == []


def test_successful_create_writes_metadata_and_indexes(tmp_path):
    saved: list[dict] = []

    def load_fn(reports_dir: Path) -> dict:
        return {}

    def save_fn(reports_dir: Path, index: dict) -> None:
        saved.append(dict(index))

    project_uuid = _create_project(tmp_path, _identity(), load_fn, save_fn)

    assert (tmp_path / project_uuid / _REPO_INFO_FILENAME).is_file()
    assert saved and list(saved[-1].values()) == [project_uuid]
