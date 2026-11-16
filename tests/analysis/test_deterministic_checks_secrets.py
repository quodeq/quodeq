"""The hardcoded-secrets checker wired into a run (S-CON-1).

Reads file text through the injected reader, stays inside the project root,
and never double-counts a secret the model already reported at that line.
"""
from __future__ import annotations

import json

import pytest

from quodeq.analysis.checks.runner import (
    CheckScope, apply_deterministic_checks, deterministic_judgments,
)
from quodeq.core.evidence.model import Evidence, PrincipleEvidence
from quodeq.data.fs.source_texts import read_source_texts
from tests.core._fake_secrets import AWS_KEY

PRINCIPLE = "Confidentiality"
STANDARD = {"id": "security", "principles": [{"name": PRINCIPLE, "requirements": [
    {"id": "S-CON-1", "text": "no hardcoded secrets", "check": "hardcoded-secrets",
     "severity": "critical"}]}]}


@pytest.fixture
def project(tmp_path):
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "settings.py").write_text(f"DEBUG = True\nAWS = '{AWS_KEY}'\n")
    (repo / "app" / "clean.py").write_text("x = 1\n")
    return repo


@pytest.fixture
def compiled_dir(tmp_path):
    out = tmp_path / "compiled"
    out.mkdir()
    (out / "security.json").write_text(json.dumps(STANDARD))
    return out


def _evidence():
    return Evidence(repository="r", language="python", date="2026-11-02",
                    source_file_count=2, files_read=2, coverage_pct=100.0)


def _apply(project, compiled_dir, evidence, tmp_path):
    jsonl = tmp_path / "run" / "evidence" / "security_evidence.jsonl"
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    scope = CheckScope(root=project, source_files=("app/settings.py", "app/clean.py"),
                       dimension="security", compiled_dir=compiled_dir)
    return apply_deterministic_checks(evidence, scope, jsonl_path=jsonl), jsonl


def test_a_declared_secrets_check_reports_the_exact_line(project, compiled_dir):
    judgments = deterministic_judgments(
        root=project, source_files=("app/settings.py", "app/clean.py"),
        dimension="security", compiled_dir=compiled_dir,
    )
    assert [(j.file, j.line, j.practice_id) for j in judgments] == [
        ("app/settings.py", 2, "S-CON-1")]


def test_the_stored_row_never_carries_the_value(project, compiled_dir, tmp_path):
    added, jsonl = _apply(project, compiled_dir, _evidence(), tmp_path)
    assert added == 1
    stored = jsonl.read_text()
    assert AWS_KEY not in stored
    assert "<REDACTED:aws_access_key>" in stored


def test_a_secret_the_model_already_reported_is_not_counted_twice(
    project, compiled_dir, tmp_path,
):
    evidence = _evidence()
    evidence.principles[PRINCIPLE] = PrincipleEvidence(
        practice_id=PRINCIPLE, display_name=PRINCIPLE, dimension="security",
        severity="critical",
        violations=[{"file": "app/settings.py", "line": 2, "req": "S-CON-1"}],
    )
    added, _ = _apply(project, compiled_dir, evidence, tmp_path)
    assert added == 0
    assert len(evidence.principles[PRINCIPLE].violations) == 1


def test_the_reader_stays_inside_the_root(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n")
    outside = tmp_path / "outside.py"
    outside.write_text("leak = 1\n")
    (root / "link.py").symlink_to(outside)

    texts = read_source_texts(root, [root / "a.py", root / "link.py", outside, root / "gone.py"])
    assert texts == [("a.py", "x = 1\n")]
