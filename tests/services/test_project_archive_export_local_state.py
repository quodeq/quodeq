"""An export carries run files only: no databases, markers, locks, restore staging or temp files."""
from __future__ import annotations

import zipfile

from quodeq.services.project_archive_export import build_project_zip


def _names(project) -> set[str]:
    path = build_project_zip(project)
    try:
        with zipfile.ZipFile(path) as zf:
            return {n.split("/", 1)[1] for n in zf.namelist()}
    finally:
        path.unlink()


def test_export_skips_databases_dotfiles_and_temp_files(tmp_path):
    project = tmp_path / "11111111-1111-4111-8111-111111111111"
    run = project / "run-1"
    (run / ".restore.tmp").mkdir(parents=True)
    keep = ["repository_info.json", "run-1/archive.tar.gz", "run-1/scalars.json", "run-1/status.json"]
    drop = ["run-1/evaluation.db", "run-1/evaluation.db-wal", "run-1/evaluation.db-shm", "run-1/.restored_at",
            "run-1/.archive.lock", "run-1/.unpacked", "run-1/.local_db", "run-1/.restore.tmp/events.jsonl",
            "run-1/archive.tar.gz.tmp"]
    for name in [*keep, *drop]:
        (project / name).write_text("x")
    assert _names(project) == set(keep) | {"manifest.json"}


def test_export_skips_run_log_agent_transcripts_and_locks(tmp_path):
    project = tmp_path / "11111111-1111-4111-8111-111111111111"
    (project / "run-1" / "evidence").mkdir(parents=True)
    keep = ["repository_info.json", "run-1/events.jsonl", "run-1/evidence/security_evidence.jsonl"]
    drop = ["run-1/run.log", "run-1/evidence/security_agent-0.stream", "run-1/evidence/security_live.stream",
            "run-1/evidence/security_agent-0.stream.err", "run-1/evidence/security_queue.lock", "dismissed.json.lock"]
    for name in [*keep, *drop]:
        (project / name).write_text("x")
    assert _names(project) == set(keep) | {"manifest.json"}


def test_export_manifest_names_no_machine_path(tmp_path):
    project = tmp_path / "11111111-1111-4111-8111-111111111111"
    project.mkdir()
    (project / "repository_info.json").write_text('{"name": "shop", "path": "/Users/alice/shop"}')
    path = build_project_zip(project)
    try:
        with zipfile.ZipFile(path) as zf:
            manifest = zf.read(f"{project.name}/manifest.json").decode()
    finally:
        path.unlink()
    assert "/Users/alice" not in manifest
