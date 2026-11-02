"""Readers that used to miss an archived run: publish, the full run read, the preview, a vanishing log."""
from __future__ import annotations

import json
import tarfile
from pathlib import Path

from quodeq.data.fs.report_parser import runs as runs_mod
from quodeq.data.fs.run_archive import archive_run, is_archived
from quodeq.data.projection.projector import Projector, ProjectionResult
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository
from quodeq.services import grade_formula_preview as gfp
from quodeq.services.shared_publish import copy_run
from tests.api._scores_routes_helpers import _scorable_violations, _seed_run

_PROJECT, _RUN = "proj", "run-1"
_EVIDENCE = "evidence/security_evidence.jsonl"


def _done_run(root: Path, *, project_after: bool = True) -> Path:
    run = _seed_run(root, _PROJECT, _RUN, _scorable_violations(5, dimension="security"), project_after=project_after)
    (run / "status.json").write_text(json.dumps({"state": "done"}))
    (run / "evaluation").mkdir()
    (run / "evaluation" / "security.json").write_text(json.dumps({
        "dimension": "security", "overallScore": 50, "overallGrade": "C",
        "principles": [], "violations": [], "totals": {"violations": 5},
    }))
    (run / "evidence").mkdir()
    (run / "evidence" / "manifest.json").write_text(json.dumps({"source_files_count": 42, "language": "python"}))
    (run / _EVIDENCE).write_text('{"snippet": "x"}\n')
    return run


def test_publishing_an_archived_run_carries_its_event_log_and_evidence(tmp_path):
    run = _done_run(tmp_path / "local")
    events = (run / "events.jsonl").read_bytes()
    evidence = (run / _EVIDENCE).read_bytes()  # CRLF on Windows: compare the bytes the run holds
    archive_run(run)
    dest = tmp_path / "clone" / _RUN
    copy_run(run, dest, with_snippets=True)  # byte for byte: the opt-in leaves the logs as they are
    with tarfile.open(dest / "archive.tar.gz", "r:gz") as tar:
        assert tar.extractfile("events.jsonl").read() == events
        assert tar.extractfile(_EVIDENCE).read() == evidence


def test_the_first_full_read_of_an_archived_run_keeps_its_evidence_metadata(tmp_path):
    run = _done_run(tmp_path)
    before = runs_mod.read_run_data(tmp_path, _PROJECT, _RUN)
    assert before[0].source_file_count == 42
    archive_run(run)
    after = runs_mod.read_run_data(tmp_path, _PROJECT, _RUN)
    assert [d.source_file_count for d in after] == [42]
    assert [d.discipline for d in after] == [d.discipline for d in before]


def test_the_preview_rescores_an_archived_run(tmp_path):
    run = _done_run(tmp_path)
    archive_run(run)
    assert is_archived(run)
    assert gfp._rescorable(run) is True


def test_an_event_log_that_vanishes_mid_projection_projects_nothing(tmp_path, monkeypatch):
    run = _done_run(tmp_path, project_after=False)
    real = Projector._detect_staleness

    def vanish_then_detect(self, store, events_path, project_dir):
        events_path.unlink()
        return real(self, store, events_path, project_dir)

    monkeypatch.setattr(Projector, "_detect_staleness", vanish_then_detect)
    result = Projector().ensure_projected(run / "events.jsonl", run, project_dir=run.parent)
    assert result == ProjectionResult(events_projected=0, rebuilt=False)


def test_a_scalar_read_falls_back_when_the_event_log_vanishes(tmp_path, monkeypatch):
    _done_run(tmp_path)

    def vanished(self):
        raise FileNotFoundError("events.jsonl")

    monkeypatch.setattr(SqliteFindingsRepository, "ensure_projected", vanished)
    sentinel = [object()]
    got = runs_mod.read_run_scalars(tmp_path, _PROJECT, _RUN, fallback_reader=lambda *a: sentinel)
    assert got is sentinel
