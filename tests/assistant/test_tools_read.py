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
        "violations": [
            {"principle": "P1", "file": "src/a.py", "line": 3, "severity": "minor",
             "title": "weak thing", "reason": "because", "snippet": "x=1", "context": "ctx"},
            {"principle": "P2", "file": "src/b.py", "line": 7, "severity": "critical",
             "title": "bad thing", "reason": "danger", "snippet": "y=2", "context": "ctx"},
            {"principle": "P1", "file": "src/c.py", "line": 9, "severity": "major",
             "title": "mid thing", "reason": "risky", "snippet": "z=3", "context": "ctx"},
        ],
        "totals": {"violations": 3}, "coveragePct": 80,
    }))
    (eval_dir / "reliability.json").write_text(json.dumps({
        "dimension": "reliability", "overallScore": 70, "overallGrade": "B",
        "principles": [{"name": "R1", "grade": "B"}],
        "violations": [
            {"principle": "R1", "file": "src/r.py", "line": 1, "severity": "major",
             "title": "rel thing", "reason": "flaky", "snippet": "q=4"},
        ],
        "totals": {"violations": 1}, "coveragePct": 90,
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
        "draft_action", "get_overview", "get_report", "get_scores", "get_standard",
        "get_violations", "list_repo_dir", "list_standards", "read_repo_file",
        "search_findings",
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


def test_get_report_includes_trimmed_violations(ctx):
    reg = build_registry(ctx)
    report = reg.dispatch("get_report", {"dimension": "security"})["result"]
    viols = report["violations"]
    assert len(viols) == 3
    # Trimmed fields only; snippet/context dropped to protect context size.
    assert set(viols[0]) == {"principle", "file", "line", "severity", "title", "reason"}
    assert all("snippet" not in v and "context" not in v for v in viols)


def test_get_report_caps_violations(ctx):
    import quodeq.assistant.tools._read_tools as rt
    eval_dir = ctx.run_dir / "evaluation"
    big = [{"principle": f"P{i}", "file": "f", "line": i, "severity": "minor",
            "title": "t", "reason": "r"} for i in range(200)]
    (eval_dir / "security.json").write_text(json.dumps({
        "dimension": "security", "overallScore": 1, "overallGrade": "F",
        "principles": [], "violations": big, "totals": {}, "coveragePct": 10,
    }))
    report = build_registry(ctx).dispatch("get_report", {"dimension": "security"})["result"]
    assert len(report["violations"]) == rt._REPORT_VIOLATION_CAP


def test_get_violations_for_dimension(ctx):
    reg = build_registry(ctx)
    out = reg.dispatch("get_violations", {"dimension": "security"})
    assert out["ok"] is True
    res = out["result"]
    # Severity-sorted: critical first, then major, then minor.
    assert [v["severity"] for v in res["violations"]] == ["critical", "major", "minor"]
    assert set(res["violations"][0]) == {"principle", "file", "line", "severity", "title", "reason"}
    assert res["by_principle"] == {"P1": 2, "P2": 1}
    assert res["dimension"] == "security"


def test_get_violations_respects_limit(ctx):
    reg = build_registry(ctx)
    out = reg.dispatch("get_violations", {"dimension": "security", "limit": 1})
    assert len(out["result"]["violations"]) == 1
    # by_principle counts reflect all violations, not just the capped page.
    assert out["result"]["by_principle"] == {"P1": 2, "P2": 1}


def test_get_violations_aggregates_across_dimensions_when_omitted(ctx):
    reg = build_registry(ctx)
    out = reg.dispatch("get_violations", {})
    assert out["ok"] is True
    res = out["result"]
    assert len(res["violations"]) == 4
    assert res["by_principle"] == {"P1": 2, "P2": 1, "R1": 1}
    assert res.get("dimension") in (None, "*")


def test_get_violations_missing_dimension_errors_helpfully(ctx):
    out = build_registry(ctx).dispatch("get_violations", {"dimension": "nope"})
    assert out["ok"] is False
    assert "get_overview" in out["error"]


def test_get_violations_without_run(ctx):
    no_run = replace(ctx, run_dir=None)
    out = build_registry(no_run).dispatch("get_violations", {"dimension": "security"})
    assert out["ok"] is False
    assert "get_overview" in out["error"]
