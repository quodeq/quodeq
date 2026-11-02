"""Publishing a project also publishes the custom standards its completed runs scored."""
import json
import subprocess

import pytest

from quodeq.services import shared_publish
from quodeq.services.standards_sharing import share_hash
from tests.services._standards_share_fixtures import _share_at, _clone, _evaluator, _local, remote  # noqa: F401 -- remote is a fixture

_DIRS = "quodeq.services._publish_standards.standard_dirs"


def _run(project, run_id, state, dims):
    run = project / run_id
    (run / "evaluation").mkdir(parents=True)
    (run / "status.json").write_text(json.dumps({"state": state, "schema_version": 2}))
    for dim in dims:
        (run / "evaluation" / f"{dim}.json").write_text(json.dumps({"dimension": dim}))


@pytest.fixture()
def project_with_run(tmp_path):
    """An evaluations root with ``proj``: one done run (android + security) and one running run."""
    root = tmp_path / "evaluations"
    _run(root / "proj", "run-1", "done", ["android", "security"])
    _run(root / "proj", "run-2", "running", ["pending"])
    return root


def _shared_ids(check):
    return sorted(p.stem for p in (check / "standards").glob("*.json"))


def test_publish_carries_scored_custom_standards(tmp_path, remote, project_with_run, monkeypatch):
    ev = tmp_path / "evaluators"
    _evaluator(ev, "android")
    _evaluator(ev, "unused")
    _evaluator(ev, "pending")  # scored only by a run that is not done
    monkeypatch.setattr(_DIRS, lambda: (None, ev))
    assert shared_publish.publish_project("proj", remote, evaluations_root=project_with_run) == 1
    check = _clone(remote, tmp_path / "check")
    assert _shared_ids(check) == ["android"]
    shared = json.loads((check / "standards" / "android.json").read_text())
    assert "managed" not in shared and shared["publishedAt"]
    assert _local(ev, "android")["shared_hash"] == share_hash(shared)
    assert "shared_hash" not in _local(ev, "unused")


def test_project_and_standards_ride_in_one_commit(tmp_path, remote, project_with_run, monkeypatch):
    ev = tmp_path / "evaluators"
    _evaluator(ev, "android")
    monkeypatch.setattr(_DIRS, lambda: (None, ev))
    shared_publish.publish_project("proj", remote, evaluations_root=project_with_run)
    check = _clone(remote, tmp_path / "check")
    out = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=check,
                         check=True, capture_output=True, text=True).stdout.split()
    assert "standards/android.json" in out
    assert any(name.startswith("evaluations/proj/run-1/") for name in out)


def test_builtin_ids_are_never_published(tmp_path, remote, project_with_run, monkeypatch):
    ev, compiled = tmp_path / "evaluators", tmp_path / "compiled"
    _evaluator(ev, "security")  # a custom file shadowing a built-in id
    _evaluator(compiled, "security")
    monkeypatch.setattr(_DIRS, lambda: (compiled, ev))
    shared_publish.publish_project("proj", remote, evaluations_root=project_with_run)
    assert not (_clone(remote, tmp_path / "check") / "standards").exists()
    assert "shared_hash" not in _local(ev, "security")


def test_publish_never_overwrites_a_newer_shared_copy(tmp_path, remote, project_with_run, monkeypatch):
    ev_a, ev_b = tmp_path / "evaluators", tmp_path / "machine-b"
    old = _evaluator(ev_a, "android")
    monkeypatch.setattr(_DIRS, lambda: (None, ev_a))
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache-b"))
    _evaluator(ev_b, "android", name="Theirs")
    _share_at("android", remote, ev_b, "2026-10-16T09:00:00Z")
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    (ev_a / "android.json").write_text(json.dumps({**old, "shared_hash": share_hash(old)}), encoding="utf-8")
    skipped = []
    shared_publish.publish_project("proj", remote, evaluations_root=project_with_run, on_skipped=skipped.extend)
    check = _clone(remote, tmp_path / "check")
    assert json.loads((check / "standards" / "android.json").read_text())["name"] == "Theirs"
    assert (check / "evaluations" / "proj" / "run-1").is_dir()
    assert skipped == ["android"]
    assert _local(ev_a, "android")["shared_hash"] == share_hash(old)


def test_unreadable_local_standard_is_skipped_not_fatal(tmp_path, remote, project_with_run, monkeypatch):
    ev = tmp_path / "evaluators"
    ev.mkdir()
    (ev / "android.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(_DIRS, lambda: (None, ev))
    assert shared_publish.publish_project("proj", remote, evaluations_root=project_with_run) == 1
    assert not (_clone(remote, tmp_path / "check") / "standards").exists()


def test_a_publish_that_failed_before_its_commit_is_retried_in_full(
        tmp_path, remote, project_with_run, monkeypatch):
    ev = tmp_path / "evaluators"
    _evaluator(ev, "android")
    monkeypatch.setattr(_DIRS, lambda: (None, ev))
    real = shared_publish.stage_standard_paths
    monkeypatch.setattr(shared_publish, "stage_standard_paths", lambda repo, ids: (False, "add failed"))
    with pytest.raises(shared_publish.PublishError):
        shared_publish.publish_project("proj", remote, evaluations_root=project_with_run)
    monkeypatch.setattr(shared_publish, "stage_standard_paths", real)
    shared_publish.publish_project("proj", remote, evaluations_root=project_with_run)
    pushed = json.loads((_clone(remote, tmp_path / "check") / "standards" / "android.json").read_text())
    assert _local(ev, "android")["shared_hash"] == share_hash(pushed)


def test_a_standard_file_that_is_not_an_object_is_skipped_with_a_warning(
        tmp_path, remote, project_with_run, monkeypatch, caplog):
    ev = tmp_path / "evaluators"
    ev.mkdir()
    (ev / "android.json").write_text("[1]", encoding="utf-8")
    monkeypatch.setattr(_DIRS, lambda: (None, ev))
    shared_publish.publish_project("proj", remote, evaluations_root=project_with_run)
    assert "android" in caplog.text and "not a JSON object" in caplog.text


def test_publish_job_reports_skipped_standards(tmp_path, monkeypatch):
    def fake(project_id, url, *, evaluations_root, env=None, on_skipped=None, with_snippets=False):
        on_skipped(["android"])
        return 2

    monkeypatch.setattr(shared_publish, "publish_project", fake)
    status = shared_publish.PublishStatus()
    assert shared_publish.get_publish_status(status)["skipped_standards"] == []
    shared_publish._do_publish("proj", "u", tmp_path, status)
    result = shared_publish.get_publish_status(status)
    assert result["state"] == "done" and result["runs"] == 2
    assert result["skipped_standards"] == ["android"]
