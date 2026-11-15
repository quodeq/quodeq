"""A publish carries no code unless the shared repository opted in; findings keep their identity."""
from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from quodeq.core.finding_identity import fingerprint, snippet_fingerprint
from quodeq.data.fs.run_archive import ARCHIVE_FILENAME, archive_run
from quodeq.data.fs.run_cold import is_cold, trim_run
from quodeq.data.fs.run_precedents import PRECEDENTS_NAME, read_precedents
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository
from quodeq.services.dismissed import dismiss_finding
from quodeq.services.shared_publish import copy_run
from tests.services._archive_fixtures import PROJECT, make_run

_CODE = "token = auth['credentials']['secret']"
_REQ = "S-CON-1"
_FINDING = {"req": _REQ, "file": "app/auth.rb", "line": 18, "snippet": _CODE, "context": f"x\n>>> {_CODE}\ny"}
_EVIDENCE = "evidence/security_evidence.jsonl"


def _run(root: Path) -> Path:
    run = make_run(root, "run-1")
    (run / "evidence").mkdir(exist_ok=True)
    (run / _EVIDENCE).write_text(json.dumps(_FINDING) + "\n")
    with open(run / "events.jsonl", "a") as fh:
        fh.write(json.dumps({"event_type": "JUDGMENT_CREATED", "payload": dict(_FINDING)}) + "\n")
    report = json.loads((run / "evaluation" / "security.json").read_text())
    report["violations"] = [dict(_FINDING)]
    (run / "evaluation" / "security.json").write_text(json.dumps(report))
    return run


def _published_text(dest: Path) -> str:
    parts = []
    for path in dest.rglob("*"):
        if path.name == ARCHIVE_FILENAME:
            with tarfile.open(path, "r:gz") as tar:
                parts += [tar.extractfile(m).read().decode() for m in tar.getmembers()]
        elif path.is_file():
            parts.append(path.read_text())
    return "".join(parts)


def _evidence_finding(dest: Path) -> dict:
    return json.loads((dest / _EVIDENCE).read_text().splitlines()[0])


def test_no_code_leaves_by_default(tmp_path):
    dest = tmp_path / "clone" / "run-1"
    copy_run(_run(tmp_path / "local"), dest)
    published = _published_text(dest)
    assert "credentials" not in published and ">>>" not in published


def test_withheld_finding_keeps_its_dismiss_identity(tmp_path):
    dest = tmp_path / "clone" / "run-1"
    copy_run(_run(tmp_path / "local"), dest)
    finding = _evidence_finding(dest)
    assert "context" not in finding
    assert snippet_fingerprint(_REQ, finding["snippet"]) == fingerprint(_REQ, _CODE)
    report = json.loads((dest / "evaluation" / "security.json").read_text())
    assert snippet_fingerprint(_REQ, report["violations"][0]["snippet"]) == fingerprint(_REQ, _CODE)


def test_archived_run_is_withheld_inside_its_archive(tmp_path):
    run = _run(tmp_path / "local")
    archive_run(run)
    local = (run / ARCHIVE_FILENAME).read_bytes()
    dest = tmp_path / "clone" / "run-1"
    copy_run(run, dest)
    assert (dest / ARCHIVE_FILENAME).is_file()
    assert "credentials" not in _published_text(dest)
    assert (run / ARCHIVE_FILENAME).read_bytes() == local  # the local archive is read, never rewritten


def test_republishing_a_withheld_archive_writes_the_same_bytes(tmp_path):
    run = _run(tmp_path / "local")
    archive_run(run)
    dest = tmp_path / "clone" / "run-1"
    copy_run(run, dest)
    first = (dest / ARCHIVE_FILENAME).read_bytes()
    copy_run(run, dest)
    assert (dest / ARCHIVE_FILENAME).read_bytes() == first


def test_opt_in_publishes_the_code(tmp_path):
    dest = tmp_path / "clone" / "run-1"
    copy_run(_run(tmp_path / "local"), dest, with_snippets=True)
    assert _evidence_finding(dest)["snippet"] == _CODE


_DISMISSED_CODE = "digest = hashlib.md5(credentials_payload)"


@pytest.fixture
def frozen_run(tmp_path, monkeypatch):
    """An archived run whose first finding (R0, f0.py line 10) is dismissed."""
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path / "qdir"))
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "qdir" / "score_cache.db"))
    run = make_run(tmp_path, "run-1", snippet=_DISMISSED_CODE)
    dismiss_finding(tmp_path / PROJECT, {"project": PROJECT, "req": "R0", "file": "f0.py", "line": 10})
    SqliteFindingsRepository(run).ensure_projected()
    archive_run(run)
    assert _DISMISSED_CODE in (run / PRECEDENTS_NAME).read_text()
    return run


@pytest.mark.parametrize("cold", [False, True], ids=["archived", "cold"])
def test_a_dismissed_finding_s_code_stays_out_of_the_precedents_sidecar(tmp_path, frozen_run, cold):
    if cold:
        trim_run(frozen_run)
        assert is_cold(frozen_run)
    local = (frozen_run / PRECEDENTS_NAME).read_bytes()
    dest = tmp_path / "clone" / "run-1"
    copy_run(frozen_run, dest)
    assert (dest / PRECEDENTS_NAME).is_file()
    assert "hashlib" not in _published_text(dest)
    assert (frozen_run / PRECEDENTS_NAME).read_bytes() == local  # the local sidecar is read, never rewritten


def test_withheld_precedents_still_match_by_fingerprint(tmp_path, frozen_run):
    dest = tmp_path / "clone" / "run-1"
    copy_run(frozen_run, dest)
    pairs = read_precedents(dest, "dismissed")
    assert [fingerprint(req, snippet) for req, snippet in pairs] == [fingerprint("R0", _DISMISSED_CODE)]
    assert read_precedents(dest, "semantic") == []  # a token is not text to embed


def test_opt_in_publishes_the_precedents_as_they_are(tmp_path, frozen_run):
    dest = tmp_path / "clone" / "run-1"
    copy_run(frozen_run, dest, with_snippets=True)
    assert (dest / PRECEDENTS_NAME).read_bytes() == (frozen_run / PRECEDENTS_NAME).read_bytes()


def test_a_malformed_precedents_sidecar_is_published_empty(tmp_path, frozen_run):
    (frozen_run / PRECEDENTS_NAME).write_text(_DISMISSED_CODE)
    dest = tmp_path / "clone" / "run-1"
    copy_run(frozen_run, dest)
    assert json.loads((dest / PRECEDENTS_NAME).read_text()) == {"version": 1, "dismissed": [], "semantic": []}
