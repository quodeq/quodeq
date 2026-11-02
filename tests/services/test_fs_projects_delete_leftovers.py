"""Deleting a project also drops its score-cache rows and its standards settings folder."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.data.fs.standards_prefs import settings_file_for_owner
from quodeq.services.fs_projects import delete_project
from quodeq.services.wiring import read_project_summary, write_project_summary
from quodeq.shared.env_paths import get_evaluations_dir

_GONE = "11111111-1111-4111-8111-111111111111"
_KEPT = "22222222-2222-4222-8222-222222222222"


def _project(reports: Path, project_id: str) -> None:
    (reports / project_id).mkdir(parents=True)
    (reports / project_id / "repository_info.json").write_text(json.dumps({"uuid": project_id, "name": project_id}))
    write_project_summary(project_id, "v1", {"grade": "B"})
    settings = settings_file_for_owner(project_id)
    settings.parent.mkdir(parents=True)
    settings.write_text("{}")


def test_delete_purges_the_project_score_cache_rows_and_settings():
    reports = Path(get_evaluations_dir())
    _project(reports, _GONE)
    _project(reports, _KEPT)

    assert delete_project(str(reports), _GONE) is True

    assert read_project_summary(_GONE, "v1") is None
    assert not settings_file_for_owner(_GONE).parent.exists()
    assert read_project_summary(_KEPT, "v1") == {"grade": "B"}
    assert settings_file_for_owner(_KEPT).is_file()


def test_delete_under_another_root_leaves_local_leftovers(tmp_path):
    # A shared clone's project ids match their pulled local copies: never purge those.
    _project(Path(get_evaluations_dir()), _GONE)
    other = tmp_path / "shared-clone" / "evaluations"
    (other / _GONE).mkdir(parents=True)
    (other / _GONE / "repository_info.json").write_text(json.dumps({"uuid": _GONE, "name": "x"}))

    assert delete_project(str(other), _GONE) is True

    assert read_project_summary(_GONE, "v1") == {"grade": "B"}
    assert settings_file_for_owner(_GONE).is_file()
