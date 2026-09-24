"""Known-id classification probes the disk only for dirs whose record did not parse."""
from __future__ import annotations

import json

import quodeq.services.fs_projects as fs_projects


def test_only_unparsed_dirs_are_probed(tmp_path, monkeypatch):
    for name in ("a", "b", "c"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "repository_info.json").write_text(json.dumps({"name": name}))
    (tmp_path / "corrupt").mkdir()
    (tmp_path / "corrupt" / "repository_info.json").write_text("{not json")
    (tmp_path / "stray").mkdir()
    probed: list[str] = []
    real = fs_projects.repository_info_exists

    def counting(project_dir):
        probed.append(project_dir.name)
        return real(project_dir)

    monkeypatch.setattr(fs_projects, "repository_info_exists", counting)

    known, info = fs_projects._classify_known_ids(
        tmp_path, ["a", "b", "c", "corrupt", "stray"], backfill=False)

    assert sorted(probed) == ["corrupt", "stray"]
    assert known.registered == {"a", "b", "c", "corrupt"}
    assert sorted(info) == ["a", "b", "c"]
