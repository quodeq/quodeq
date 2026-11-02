"""A shared publish never carries the publisher's machine paths."""
import json
from pathlib import Path

from quodeq.services.publish_scrub import published_repository_info, scrub_report_paths
from quodeq.services.shared_publish import stage_project

_PUBLISHER_PATH = "/Users/alice/work/shop"


def _local_project(root: Path) -> Path:
    project = root / "local" / "proj-uuid"
    run = project / "r1"
    (run / "evaluation").mkdir(parents=True)
    (project / "repository_info.json").write_text(json.dumps({
        "uuid": "proj-uuid", "name": "shop", "location": "local", "path": _PUBLISHER_PATH,
        "originUrl": "https://github.com/acme/shop.git",
    }))
    (run / "status.json").write_text(json.dumps({"state": "done", "schema_version": 2}))
    (run / "events.jsonl").write_text('{"event_type":"RUN_STARTED"}\n')
    (run / "evaluation" / "security.json").write_text(json.dumps({"dimension": "security", "project": _PUBLISHER_PATH}))
    return project


def test_stage_project_publishes_no_machine_path(tmp_path):
    dest = tmp_path / "clone" / "evaluations" / "proj-uuid"
    stage_project(_local_project(tmp_path), dest)
    info = json.loads((dest / "repository_info.json").read_text())
    assert info["path"] == ""  # still a string: import requires one
    assert info["originUrl"] == "https://github.com/acme/shop.git"
    assert json.loads((dest / "r1" / "evaluation" / "security.json").read_text())["project"] == "shop"
    published = "".join(p.read_text() for p in dest.rglob("*") if p.is_file())
    assert "/Users/alice" not in published


def test_stage_project_leaves_local_files_untouched(tmp_path):
    project = _local_project(tmp_path)
    stage_project(project, tmp_path / "clone" / "evaluations" / "proj-uuid")
    assert json.loads((project / "repository_info.json").read_text())["path"] == _PUBLISHER_PATH
    report = json.loads((project / "r1" / "evaluation" / "security.json").read_text())
    assert report["project"] == _PUBLISHER_PATH


def test_online_project_keeps_its_repository_url():
    info = {"name": "shop", "location": "online", "path": "https://github.com/acme/shop.git"}
    assert published_repository_info(info) == info


def test_windows_publisher_path_is_blanked():
    info = {"name": "shop", "location": "local", "path": "C:\\Users\\alice\\shop"}
    assert published_repository_info(info)["path"] == ""


def test_report_with_windows_path_names_only_the_folder(tmp_path):
    report = tmp_path / "security.json"
    report.write_text(json.dumps({"project": "C:\\Users\\alice\\shop"}))
    scrub_report_paths([report])
    assert json.loads(report.read_text())["project"] == "shop"
