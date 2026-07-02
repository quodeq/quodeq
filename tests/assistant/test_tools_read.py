import json
from dataclasses import replace
from pathlib import Path

import pytest

from quodeq.assistant.tools import ToolContext, build_registry
from quodeq.data.sqlite.assistant_repository import AssistantRepository
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository


def _finding(**over):
    # FindingsRouter wire dict: short keys per finding_dict_to_row
    # (src/quodeq/data/sqlite/_row_mappers.py).
    base = {
        "p": "req-1", "d": "security", "req": "req-1",
        "t": "violation", "severity": "major", "file": "src/a.py",
        "line": 3, "end_line": 3, "w": "t", "reason": "sql injection risk",
        "snippet": "cur.execute(q)", "vt": "code", "context": "",
        "scope": "file", "req_refs": [], "confidence": 90,
        "provenance_downgrade": 0,
    }
    base.update(over)
    return base


@pytest.fixture()
def ctx(tmp_path):
    run_dir = tmp_path / "run"
    findings = SqliteFindingsRepository(run_dir)
    findings.insert_finding(_finding())
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(parents=True)
    (eval_dir / "security.json").write_text(json.dumps({
        "dimension": "security", "overallScore": 61.5, "overallGrade": "C",
        "principles": [{"name": "P1", "grade": "C"}],
        "totals": {"violations": 1}, "coveragePct": 80,
    }))
    repo = AssistantRepository(tmp_path / "assistant.db")
    repo.create_session(session_id="s1", provider="ollama")
    return ToolContext(
        repository=repo, session_id="s1", run_dir=run_dir, repo_root=None,
        evaluators_dir=tmp_path / "evaluators", compiled_dir=tmp_path / "compiled",
        dimensions_file=tmp_path / "dimensions.json",
    )


def test_registry_registers_expected_tools(ctx):
    reg = build_registry(ctx)
    assert reg.names() == [
        "draft_action", "get_report", "get_scores", "get_standard",
        "list_repo_dir", "list_standards", "read_repo_file", "search_findings",
    ]


def test_search_findings(ctx):
    reg = build_registry(ctx)
    out = reg.dispatch("search_findings", {"query": "sql injection"})
    assert out["ok"] is True
    (hit,) = out["result"]["findings"]
    assert hit["file"] == "src/a.py"
    assert hit["severity"] == "major"
    assert hit["dimension"] == "security"
    assert hit["requirement"] == "req-1"


def test_search_findings_without_run(ctx):
    no_run = replace(ctx, run_dir=None)
    out = build_registry(no_run).dispatch("search_findings", {"query": "x"})
    assert out["ok"] is False
    assert "no run" in out["error"]


def test_get_scores_and_report(ctx):
    reg = build_registry(ctx)
    scores = reg.dispatch("get_scores", {})
    assert scores["result"]["security"] == {"score": 61.5, "grade": "C"}
    report = reg.dispatch("get_report", {"dimension": "security"})
    assert report["result"]["principles"] == [{"name": "P1", "grade": "C"}]
    missing = reg.dispatch("get_report", {"dimension": "nope"})
    assert missing["ok"] is False
