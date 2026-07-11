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
        "draft_action", "get_context", "get_overview", "get_report", "get_scores",
        "get_standard", "get_violations", "list_repo_dir", "list_standards",
        "read_repo_file", "search_findings",
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


def _req_ctx(tmp_path):
    """A run whose eval JSON carries `req` on one violation and omits it on another."""
    run_dir = tmp_path / "run"
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(parents=True)
    (eval_dir / "security.json").write_text(json.dumps({
        "dimension": "security", "overallScore": 50, "overallGrade": "C",
        "principles": [{"name": "P1", "grade": "C"}],
        "violations": [
            {"principle": "P1", "req": "M-1", "file": "a.py", "line": 3,
             "severity": "critical", "title": "t", "reason": "r"},
            {"principle": "P2", "file": "b.py", "line": 7,  # no req key
             "severity": "major", "title": "t2", "reason": "r2"},
        ],
        "totals": {"violations": 2},
    }))
    repo = AssistantRepository(tmp_path / "assistant.db")
    repo.create_session(session_id="s1", provider="ollama")
    return ToolContext(
        repository=repo, session_id="s1", run_dir=run_dir, repo_root=None,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json")


def test_get_report_exposes_requirement(tmp_path):
    # get_report must surface `requirement` so the model can form a correct
    # dismiss/verify key. A finding with no req exposes "" (not missing/None).
    reg = build_registry(_req_ctx(tmp_path))
    viols = reg.dispatch("get_report", {"dimension": "security"})["result"]["violations"]
    by_file = {v["file"]: v for v in viols}
    assert by_file["a.py"]["requirement"] == "M-1"
    assert by_file["b.py"]["requirement"] == ""


def test_get_violations_exposes_requirement(tmp_path):
    reg = build_registry(_req_ctx(tmp_path))
    viols = reg.dispatch("get_violations", {"dimension": "security"})["result"]["violations"]
    by_file = {v["file"]: v for v in viols}
    assert by_file["a.py"]["requirement"] == "M-1"
    assert by_file["b.py"]["requirement"] == ""


def test_search_findings_limit_floor_clamped(ctx):
    # limit=0 (or negative) must not reach the repo -- clamp to >=1 instead.
    reg = build_registry(ctx)
    out = reg.dispatch("search_findings", {"query": "sql injection", "limit": 0})
    assert out["ok"] is True
    assert len(out["result"]["findings"]) == 1


def test_search_findings_without_run(ctx):
    no_run = replace(ctx, run_dir=None)
    out = build_registry(no_run).dispatch("search_findings", {"query": "x"})
    assert out["ok"] is False
    assert "get_context" in out["error"]
    assert "get_violations" in out["error"]


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
    # `requirement` is included so the model can form a dismiss/verify key.
    assert set(viols[0]) == {"principle", "requirement", "file", "line",
                             "severity", "title", "reason"}
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
    assert set(res["violations"][0]) == {"principle", "requirement", "file", "line",
                                         "severity", "title", "reason"}
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
    assert "get_context" in out["error"]


# --- Accumulated (per-dimension-latest) scope: no specific run selected. ------
# The overview picks each dimension's LATEST run independently, so the payload
# spans several runs (fromRunId differs) and keys the principle as "practiceId"
# (serialized Finding) rather than the raw run JSON's "principle".
_ACC = {
    "project": "p",
    "dimensions": [
        {"dimension": "security", "overallScore": "9.6/10", "overallGrade": "Exemplary",
         "fromRunId": "runA", "principles": [{"principle": "S1", "grade": "A"}],
         "totals": {"violations": 2}, "coveragePct": 80,
         "violations": [
             {"practiceId": "S1", "file": "a.kt", "line": 1, "severity": "minor",
              "title": "t1", "reason": "r1", "snippet": "x", "context": "c"},
             {"practiceId": "S2", "file": "b.kt", "line": 2, "severity": "critical",
              "title": "t2", "reason": "r2"},
         ]},
        {"dimension": "reliability", "overallScore": "9.0/10", "overallGrade": "Exemplary",
         "fromRunId": "runB", "principles": [{"principle": "R1", "grade": "A"}],
         "totals": {"violations": 1},
         "violations": [
             {"practiceId": "R1", "file": "r.kt", "line": 3, "severity": "major",
              "title": "t3", "reason": "r3"},
         ]},
    ],
}


@pytest.fixture()
def acc_ctx(tmp_path, monkeypatch):
    repo = AssistantRepository(tmp_path / "assistant.db")
    repo.create_session(session_id="s1", provider="ollama")
    monkeypatch.setattr(
        "quodeq.assistant.tools._read_tools._fs_reports.get_accumulated",
        lambda reports_dir, project, as_of: _ACC)
    return ToolContext(
        repository=repo, session_id="s1", run_dir=None, repo_root=None,
        evaluators_dir=tmp_path / "evaluators", compiled_dir=tmp_path / "compiled",
        dimensions_file=tmp_path / "dimensions.json",
        project_id="p", reports_dir=tmp_path / "reports",
    )


def test_get_scores_accumulated(acc_ctx):
    out = build_registry(acc_ctx).dispatch("get_scores", {})["result"]
    # Each dimension carries its own source run — they can differ.
    assert out["security"] == {"score": "9.6/10", "grade": "Exemplary", "fromRun": "runA"}
    assert out["reliability"] == {"score": "9.0/10", "grade": "Exemplary", "fromRun": "runB"}


def test_get_report_accumulated(acc_ctx):
    out = build_registry(acc_ctx).dispatch("get_report", {"dimension": "security"})["result"]
    assert out["overallGrade"] == "Exemplary"
    assert out["fromRun"] == "runA"
    # `principle` is normalized to also carry `name` so callers don't need to
    # know which scope (run vs. accumulated) they're reading.
    assert out["principles"] == [{"principle": "S1", "grade": "A", "name": "S1"}]
    # practiceId is normalized to `principle`; snippet/context dropped.
    assert {v["principle"] for v in out["violations"]} == {"S1", "S2"}
    assert all("snippet" not in v and "context" not in v for v in out["violations"])
    # DimensionResult has no coverage field -- omit rather than return a key
    # that's always null in this scope.
    assert "coveragePct" not in out


def test_get_report_accumulated_unknown_dimension(acc_ctx):
    out = build_registry(acc_ctx).dispatch("get_report", {"dimension": "nope"})
    assert out["ok"] is False
    assert "reliability" in out["error"] and "security" in out["error"]


def test_get_violations_accumulated_for_dimension(acc_ctx):
    res = build_registry(acc_ctx).dispatch("get_violations", {"dimension": "security"})["result"]
    # Severity-sorted (critical first), practiceId normalized to principle.
    assert [v["severity"] for v in res["violations"]] == ["critical", "minor"]
    assert res["by_principle"] == {"S1": 1, "S2": 1}
    assert res["dimension"] == "security"


def test_get_violations_accumulated_aggregates_when_omitted(acc_ctx):
    res = build_registry(acc_ctx).dispatch("get_violations", {})["result"]
    assert res["count"] == 3
    assert res["by_principle"] == {"S1": 1, "S2": 1, "R1": 1}


def test_get_scores_no_scope_errors(tmp_path):
    # No run AND no project scope → a clear error, not a crash.
    repo = AssistantRepository(tmp_path / "assistant.db")
    repo.create_session(session_id="s1", provider="ollama")
    ctx = ToolContext(
        repository=repo, session_id="s1", run_dir=None, repo_root=None,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json", project_id=None, reports_dir=None,
    )
    out = build_registry(ctx).dispatch("get_scores", {})
    assert out["ok"] is False
    assert "get_context" in out["error"]
