"""A publish carries no code unless the shared repository opted in; findings keep their identity."""
from __future__ import annotations

import json
import tarfile
from pathlib import Path

from quodeq.core.finding_identity import fingerprint, snippet_fingerprint
from quodeq.data.fs.run_archive import ARCHIVE_FILENAME, archive_run
from quodeq.services.shared_publish import copy_run
from tests.services._archive_fixtures import make_run

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
