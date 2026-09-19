"""``PrecedentAutoDismisser`` records a real dismissal for a cross-file exact
precedent match (#1208), so the finding leaves the score through the same
seam a manual dismissal uses and shows in the Dismissed tab with a reason.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.core.finding_identity import snippet_fingerprint
from quodeq.services.dismissed import dismiss_finding, dismissed_keys, restore_finding
from quodeq.services.precedent_dismiss import PRECEDENT_REASON, PrecedentAutoDismisser

SNIPPET = "password = 'hunter2'"
REQ = "S-CON-1"


def _finding(file: str, line: int = 5, snippet: str | None = SNIPPET) -> dict:
    return {"t": "violation", "req": REQ, "p": "Confidentiality", "file": file, "line": line, "snippet": snippet}


@pytest.fixture
def project(tmp_path: Path) -> Path:
    dismiss_finding(tmp_path, {"req": REQ, "file": "src/a.py", "line": 5, "snippet": SNIPPET, "dismissReason": "test fixture"})
    return tmp_path


def test_cross_file_match_is_dismissed_with_the_precedent_reason(project: Path) -> None:
    dismisser = PrecedentAutoDismisser(project)
    assert dismisser.record(_finding("src/b.py")) is True
    state = dismissed_keys(project)
    assert state.matches(req=REQ, file="src/b.py", line=5, snippet=SNIPPET)
    entry = next(e for e in state.entries if e.file == "src/b.py")
    assert entry.reason == PRECEDENT_REASON
    assert entry.fingerprint == snippet_fingerprint(REQ, SNIPPET)


def test_same_file_match_is_already_dismissed_so_nothing_is_written(project: Path) -> None:
    before = len(dismissed_keys(project))
    assert PrecedentAutoDismisser(project).record(_finding("src/a.py", line=99)) is False
    assert len(dismissed_keys(project)) == before


def test_restored_code_is_never_auto_dismissed(project: Path) -> None:
    restore_finding(project, {"req": REQ, "file": "src/a.py", "line": 5})
    assert PrecedentAutoDismisser(project).record(_finding("src/b.py")) is False
    assert not dismissed_keys(project).matches(req=REQ, file="src/b.py", line=5, snippet=SNIPPET)


def test_each_key_is_recorded_once(project: Path) -> None:
    dismisser = PrecedentAutoDismisser(project)
    assert dismisser.record(_finding("src/b.py", line=5)) is True
    assert dismisser.record(_finding("src/b.py", line=40)) is False
    assert sum(1 for e in dismissed_keys(project).entries if e.file == "src/b.py") == 1


def test_snippetless_findings_have_no_precedent_identity(project: Path) -> None:
    assert PrecedentAutoDismisser(project).record(_finding("src/b.py", snippet=None)) is False


def test_compliance_is_never_dismissed(project: Path) -> None:
    finding = _finding("src/b.py")
    finding["t"] = "compliance"
    assert PrecedentAutoDismisser(project).record(finding) is False
