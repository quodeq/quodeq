"""Assistant read tools against a run scope: registry, search, reports, violations."""
import json
from dataclasses import replace

import pytest

from quodeq.assistant.tools import ToolContext, build_registry
from quodeq.data.sqlite.assistant_repository import AssistantRepository

from ._tools_read_helpers import _run_ctx


@pytest.fixture()
def ctx(tmp_path):
    return _run_ctx(tmp_path)


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
    assert scores["result"]["scores"]["security"] == {"score": 61.5, "grade": "C"}
    assert scores["result"]["hiddenStandardIds"] == []
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


def test_get_violations_page_keeps_severity_order_and_stable_ties(ctx, monkeypatch):
    """The page is the first `limit` of the severity-sorted list, ties in input
    order, exactly as sorted()[:limit] gave before the top-k selection."""
    from quodeq.assistant.tools import _read_tools_violations as rv
    raw = [{"principle": "P", "file": f"src/f{i}.py", "line": i, "severity": "minor",
            "title": "t", "reason": "r"} for i in range(10)]
    raw.append({"principle": "P", "file": "src/crit.py", "line": 99, "severity": "critical",
                "title": "t", "reason": "r"})
    monkeypatch.setattr(rv, "_violations_from_run", lambda c, d: (raw, "security", []))
    out = rv._get_violations(ctx, "security", limit=5)
    assert [v["file"] for v in out["violations"]] == [
        "src/crit.py", "src/f0.py", "src/f1.py", "src/f2.py", "src/f3.py"]
    assert out["count"] == 11


def test_get_violations_aggregates_across_dimensions_when_omitted(ctx):
    reg = build_registry(ctx)
    out = reg.dispatch("get_violations", {})
    assert out["ok"] is True
    res = out["result"]
    assert len(res["violations"]) == 4
    assert res["by_principle"] == {"P1": 2, "P2": 1, "R1": 1}
    assert res.get("dimension") in (None, "*")


def test_get_report_rejects_traversal_dimension(ctx):
    """The model-controlled `dimension` argument must never reach the
    filesystem: traversal and absolute paths are rejected up front."""
    # Plant a JSON file OUTSIDE the evaluation dir that a traversal would hit.
    (ctx.run_dir / "secret.json").write_text(json.dumps({"stolen": True}))
    reg = build_registry(ctx)
    for evil in ("../secret", "../../other/secrets", "/etc/passwd", "a/b", "UPPER"):
        out = reg.dispatch("get_report", {"dimension": evil})
        assert out["ok"] is False
        assert "invalid dimension" in out["error"]


def test_get_violations_rejects_traversal_dimension(ctx):
    reg = build_registry(ctx)
    out = reg.dispatch("get_violations", {"dimension": "../secret"})
    assert out["ok"] is False
    assert "invalid dimension" in out["error"]


def test_get_violations_missing_dimension_errors_helpfully(ctx):
    out = build_registry(ctx).dispatch("get_violations", {"dimension": "nope"})
    assert out["ok"] is False
    assert "get_overview" in out["error"]


def test_get_violations_without_run(ctx):
    no_run = replace(ctx, run_dir=None)
    out = build_registry(no_run).dispatch("get_violations", {"dimension": "security"})
    assert out["ok"] is False
    assert "get_context" in out["error"]
