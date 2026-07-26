import json
from dataclasses import replace
from pathlib import Path

import pytest

from quodeq.assistant.tools import ToolContext, ToolError, build_registry
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


def _run_ctx(tmp_path, visible_standard_ids=None, findings=None):
    """A run-scoped ctx with "security" and "reliability" evaluation reports.

    `findings` overrides the SQL findings seeded for search_findings (default:
    a single "security" finding); `visible_standard_ids` plumbs the visibility
    selection through, mirroring `_standards_ctx` below.
    """
    run_dir = tmp_path / "run"
    repo_findings = SqliteFindingsRepository(run_dir)
    for f in (findings if findings is not None else [_finding()]):
        repo_findings.insert_finding(f)
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
        visible_standard_ids=visible_standard_ids,
    )


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


def _acc_ctx(tmp_path, monkeypatch, visible_standard_ids=None):
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
        visible_standard_ids=visible_standard_ids,
    )


@pytest.fixture()
def acc_ctx(tmp_path, monkeypatch):
    return _acc_ctx(tmp_path, monkeypatch)


def test_get_scores_accumulated(acc_ctx):
    out = build_registry(acc_ctx).dispatch("get_scores", {})["result"]
    # Each dimension carries its own source run — they can differ.
    assert out["scores"]["security"] == {"score": "9.6/10", "grade": "Exemplary", "fromRun": "runA"}
    assert out["scores"]["reliability"] == {"score": "9.0/10", "grade": "Exemplary", "fromRun": "runB"}
    assert out["hiddenStandardIds"] == []


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


# --- list_standards / get_standard visibility filtering. ---------------------


def _standards_ctx(tmp_path, visible_standard_ids=None):
    """A ctx whose StandardsService sees two custom standards: "security" and
    "clean-architecture". evaluators_dir is real (glob'd by list_custom());
    dimensions_file/compiled_dir are left non-existent so list_builtin()
    degrades to [] and only the custom pair is in play."""
    evaluators_dir = tmp_path / "evaluators"
    evaluators_dir.mkdir(parents=True)
    for sid in ("security", "clean-architecture"):
        (evaluators_dir / f"{sid}.json").write_text(json.dumps({
            "id": sid, "name": sid, "principles": [],
        }))
    repo = AssistantRepository(tmp_path / "assistant.db")
    repo.create_session(session_id="s1", provider="ollama")
    return ToolContext(
        repository=repo, session_id="s1", run_dir=None, repo_root=None,
        evaluators_dir=evaluators_dir, compiled_dir=tmp_path / "compiled",
        dimensions_file=tmp_path / "dimensions.json",
        visible_standard_ids=visible_standard_ids,
    )


def test_list_standards_hides_deselected(tmp_path):
    from quodeq.assistant.tools._read_tools import _list_standards
    ctx = _standards_ctx(tmp_path, visible_standard_ids=("security",))
    out = _list_standards(ctx)
    assert [s["id"] for s in out["standards"]] == ["security"]
    assert "clean-architecture" in out["hiddenStandardIds"]


def test_list_standards_include_hidden_returns_everything(tmp_path):
    from quodeq.assistant.tools._read_tools import _list_standards
    ctx = _standards_ctx(tmp_path, visible_standard_ids=("security",))
    out = _list_standards(ctx, include_hidden=True)
    ids = [s["id"] for s in out["standards"]]
    assert "security" in ids and "clean-architecture" in ids
    assert "clean-architecture" in out["hiddenStandardIds"]


def test_list_standards_unfiltered_when_selection_is_none(tmp_path):
    from quodeq.assistant.tools._read_tools import _list_standards
    out = _list_standards(_standards_ctx(tmp_path, visible_standard_ids=None))
    assert out["hiddenStandardIds"] == []


def test_list_standards_empty_tuple_hides_everything(tmp_path):
    # visible_standard_ids=() is a real selection ("hide everything"), distinct
    # from None ("no filtering"). Must never be treated as falsy-equals-None.
    from quodeq.assistant.tools._read_tools import _list_standards
    ctx = _standards_ctx(tmp_path, visible_standard_ids=())
    out = _list_standards(ctx)
    assert out["standards"] == []
    assert set(out["hiddenStandardIds"]) == {"security", "clean-architecture"}


def test_get_standard_still_reaches_a_hidden_standard(tmp_path):
    """The by-name escape hatch: hidden data stays reachable on explicit ask."""
    from quodeq.assistant.tools._read_tools import _get_standard
    ctx = _standards_ctx(tmp_path, visible_standard_ids=("security",))
    assert _get_standard(ctx, "clean-architecture")["id"] == "clean-architecture"


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


# --- Hidden-standard filtering: get_scores / get_violations / search_findings.
# Both `ctx` (run scope) and `acc_ctx` (accumulated scope) fixtures carry two
# dimensions, "security" and "reliability"; these tests hide "reliability" and
# confirm it disappears from aggregate reads but is still reachable by name.


def test_get_scores_excludes_hidden_dimensions_run_scope(tmp_path):
    from quodeq.assistant.tools._read_tools import _get_scores
    ctx = _run_ctx(tmp_path, visible_standard_ids=("security",))
    out = _get_scores(ctx)
    assert set(out["scores"]) == {"security"}
    assert out["hiddenStandardIds"] == ["reliability"]


def test_get_scores_excludes_hidden_dimensions_accumulated(tmp_path, monkeypatch):
    from quodeq.assistant.tools._read_tools import _get_scores
    ctx = _acc_ctx(tmp_path, monkeypatch, visible_standard_ids=("security",))
    out = _get_scores(ctx)
    assert set(out["scores"]) == {"security"}
    assert out["hiddenStandardIds"] == ["reliability"]


def test_get_scores_no_selection_means_no_filtering(tmp_path, monkeypatch):
    from quodeq.assistant.tools._read_tools import _get_scores
    out = _get_scores(_acc_ctx(tmp_path, monkeypatch, visible_standard_ids=None))
    assert "reliability" in out["scores"]
    assert out["hiddenStandardIds"] == []


def test_get_scores_filename_fallback_survives_filtering(tmp_path):
    """A report file with no "dimension" key is keyed by its filename, not
    dropped -- even once filtering is applied. Guards `_raw_run_dims`, which
    exists specifically to preserve this behaviour through the new filter."""
    from quodeq.assistant.tools._read_tools import _get_scores
    ctx = _run_ctx(tmp_path, visible_standard_ids=None)
    eval_dir = ctx.run_dir / "evaluation"
    (eval_dir / "no-dim-field.json").write_text(json.dumps({
        "overallScore": 42, "overallGrade": "D", "violations": [],
    }))
    out = _get_scores(ctx)
    assert out["scores"]["no-dim-field"] == {"score": 42, "grade": "D"}


def test_get_violations_excludes_hidden_dimensions_run_scope(tmp_path):
    from quodeq.assistant.tools._read_tools import _get_violations
    ctx = _run_ctx(tmp_path, visible_standard_ids=("security",))
    out = _get_violations(ctx)
    # reliability's R1 is excluded; only security's P1/P2 counts remain.
    assert out["by_principle"] == {"P1": 2, "P2": 1}
    assert out["hiddenStandardIds"] == ["reliability"]


def test_get_violations_named_hidden_dimension_still_works_run_scope(tmp_path):
    """Explicitly naming a hidden dimension is the deliberate escape hatch."""
    from quodeq.assistant.tools._read_tools import _get_violations
    ctx = _run_ctx(tmp_path, visible_standard_ids=("security",))
    out = _get_violations(ctx, dimension="reliability")
    assert out["dimension"] == "reliability"
    assert out["count"] == 1
    assert out["hiddenStandardIds"] == []


def test_get_violations_excludes_hidden_dimensions_accumulated(tmp_path, monkeypatch):
    from quodeq.assistant.tools._read_tools import _get_violations
    ctx = _acc_ctx(tmp_path, monkeypatch, visible_standard_ids=("security",))
    out = _get_violations(ctx)
    assert out["by_principle"] == {"S1": 1, "S2": 1}
    assert out["hiddenStandardIds"] == ["reliability"]


def test_get_violations_named_hidden_dimension_still_works_accumulated(tmp_path, monkeypatch):
    from quodeq.assistant.tools._read_tools import _get_violations
    ctx = _acc_ctx(tmp_path, monkeypatch, visible_standard_ids=("security",))
    out = _get_violations(ctx, dimension="reliability")
    assert out["dimension"] == "reliability"
    assert out["count"] > 0
    assert out["hiddenStandardIds"] == []


def test_search_findings_excludes_hidden_dimensions(tmp_path):
    from quodeq.assistant.tools._read_tools import _search_findings
    findings = [
        _finding(),  # dimension "security", reason "sql injection risk"
        _finding(d="reliability", p="req-2", req="req-2", file="src/r.py",
                 reason="reliability risk"),
    ]
    ctx = _run_ctx(tmp_path, visible_standard_ids=("security",), findings=findings)
    out = _search_findings(ctx, query="risk")
    assert len(out["findings"]) == 1
    assert all(f["dimension"] == "security" for f in out["findings"])
    assert out["hiddenStandardIds"] == ["reliability"]


def test_search_findings_no_selection_means_no_filtering(tmp_path):
    from quodeq.assistant.tools._read_tools import _search_findings
    findings = [
        _finding(),
        _finding(d="reliability", p="req-2", req="req-2", file="src/r.py",
                 reason="reliability risk"),
    ]
    ctx = _run_ctx(tmp_path, visible_standard_ids=None, findings=findings)
    out = _search_findings(ctx, query="risk")
    assert {f["dimension"] for f in out["findings"]} == {"security", "reliability"}
    assert out["hiddenStandardIds"] == []


# --- get_report / get_violations not-found errors never name hidden dims. ----


def test_report_not_found_error_does_not_name_hidden_dimensions(tmp_path, monkeypatch):
    from quodeq.assistant.tools._read_tools import _get_report
    ctx = _acc_ctx(tmp_path, monkeypatch, visible_standard_ids=("security",))
    with pytest.raises(ToolError) as exc:
        _get_report(ctx, "usability")
    assert "reliability" not in str(exc.value)
    assert "security" in str(exc.value)


def test_violations_not_found_error_does_not_name_hidden_dimensions(tmp_path, monkeypatch):
    from quodeq.assistant.tools._read_tools import _get_violations
    ctx = _acc_ctx(tmp_path, monkeypatch, visible_standard_ids=("security",))
    with pytest.raises(ToolError) as exc:
        _get_violations(ctx, dimension="usability")
    assert "reliability" not in str(exc.value)
    assert "security" in str(exc.value)

