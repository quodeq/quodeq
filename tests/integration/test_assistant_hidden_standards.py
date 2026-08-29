"""Issue #883: the assistant must not answer with standards the dashboard hides.

Pins the issue's own reproduction end to end: once a standard is hidden via
`save_visible_standard_ids`, it must disappear from every general-purpose
read tool (get_overview, get_scores, list_standards) while staying reachable
when named explicitly (get_standard, get_violations) -- the deliberate escape
hatch. Also pins that the overview's summary omits `overallGrade` and
`numericAverage` once anything is filtered: the dashboard derives those from
trend data in JS, so a Python-computed value here could contradict the
screen.

Dispatches through the real `ToolRegistry` (`quodeq.assistant.tools.build_registry`
+ `ToolRegistry.dispatch`), the same seam the MCP server and the CLI/API
adapters use, rather than calling the private `_get_overview`/`_get_scores`/
`_list_standards` functions directly -- this proves the wiring the model
actually goes through, matching the pattern in
tests/assistant/test_registry.py and tests/assistant/test_tools_read.py.

No `@pytest.mark.integration` marker: nothing here spawns a real subprocess
or needs an external resource (accumulated report data is monkeypatched at
the same `_fs_reports.get_accumulated` seam tests/assistant/test_tools_overview.py
and test_tools_read.py already use; everything else is tmp_path + sqlite),
matching every other file already in tests/integration/ (see e.g. the module
docstrings of test_assistant_end_to_end.py and test_assistant_cli_end_to_end.py):
CI runs with `-m "not integration"`, which only deselects marked tests, so
this one still runs.
"""
import json

from quodeq.assistant.tools import ToolContext, build_registry
from quodeq.data.fs.standards_prefs import load_visible_standard_ids, save_visible_standard_ids
from quodeq.data.sqlite.assistant_repository import AssistantRepository

# Accumulated (cross-run) payload backing get_overview/get_scores/get_violations
# in this file: three dimensions, one of which ("clean-architecture") the
# tests below hide via the saved visibility selection.
_ACCUMULATED = {
    "project": "acme",
    "dimensions": [
        {
            "dimension": "security", "overallScore": 72, "overallGrade": "C",
            "trend": "up",
            "violations": [{"severity": "critical"}, {"severity": "major"}],
        },
        {
            "dimension": "reliability", "overallScore": 80, "overallGrade": "B",
            "trend": "flat",
            "violations": [{"severity": "minor"}],
        },
        {
            "dimension": "clean-architecture", "overallScore": 88, "overallGrade": "B",
            "trend": None,
            "violations": [{"severity": "minor"}],
        },
    ],
    "summary": {
        "overallGrade": "B", "numericAverage": 80.0, "previousNumericAverage": 78.0,
        "totalViolations": 4, "totalCompliance": 40, "dimensionCount": 3,
        "severity": {"critical": 1, "major": 1, "minor": 2},
    },
}


def _evaluators_dir(tmp_path):
    """Real on-disk custom-standard files, glob'd by StandardsService.list_custom()
    (matching tests/assistant/test_tools_read.py::_standards_ctx) so
    list_standards/get_standard have real data to filter and fetch, not a mock."""
    evaluators_dir = tmp_path / "evaluators"
    evaluators_dir.mkdir(parents=True)
    for sid in ("security", "reliability", "clean-architecture"):
        (evaluators_dir / f"{sid}.json").write_text(json.dumps({
            "id": sid, "name": sid, "principles": [],
        }))
    return evaluators_dir


def _build_registry(tmp_path, repo_root, monkeypatch):
    """An accumulated-scope registry (no run_dir selected -- the default
    dashboard/overview view) whose visible_standard_ids is loaded through the
    REAL load path: `load_visible_standard_ids(repo_root)`, the same call
    `_build_registry_from_args` makes in quodeq.assistant.mcp.server, rather
    than hand-setting the tuple.

    get_overview/get_scores read accumulated data through
    `services._fs_reports.get_accumulated`; that function's own filesystem
    behaviour is covered elsewhere (services tests), so it is monkeypatched
    here exactly as tests/assistant/test_tools_overview.py and
    test_tools_read.py's `acc_ctx` already do -- this test's job is the
    hidden-standards wiring on top of it, not re-proving accumulation.
    """
    monkeypatch.setattr(
        "quodeq.assistant.tools._overview.get_accumulated",
        lambda *a: _ACCUMULATED)
    monkeypatch.setattr(
        "quodeq.assistant.tools._read_tools._fs_reports.get_accumulated",
        lambda *a: _ACCUMULATED)
    repo = AssistantRepository(tmp_path / "assistant.db")
    repo.create_session(session_id="s1", provider="ollama")
    ctx = ToolContext(
        repository=repo, session_id="s1", run_dir=None, repo_root=repo_root,
        evaluators_dir=_evaluators_dir(tmp_path), compiled_dir=tmp_path / "compiled",
        dimensions_file=tmp_path / "dimensions.json",
        project_id="acme", reports_dir=tmp_path / "reports",
        visible_standard_ids=load_visible_standard_ids(repo_root),
    )
    return build_registry(ctx)


def test_hidden_standard_is_absent_from_every_general_answer(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    save_visible_standard_ids(repo_root, ["security", "reliability"])

    registry = _build_registry(tmp_path, repo_root, monkeypatch)

    overview_out = registry.dispatch("get_overview", {})
    scores_out = registry.dispatch("get_scores", {})
    standards_out = registry.dispatch("list_standards", {})
    assert overview_out["ok"], overview_out
    assert scores_out["ok"], scores_out
    assert standards_out["ok"], standards_out
    overview, scores, standards = (
        overview_out["result"], scores_out["result"], standards_out["result"])

    assert [d["dimension"] for d in overview["dimensions"]] == ["security", "reliability"]
    assert set(scores["scores"]) == {"security", "reliability"}
    assert {s["id"] for s in standards["standards"]} == {"security", "reliability"}

    for payload in (overview, scores, standards):
        assert payload["hiddenStandardIds"] == ["clean-architecture"]
        assert "clean-architecture" not in json.dumps(
            [d for k, d in payload.items() if k != "hiddenStandardIds"])

    # Deliberate omission: the dashboard derives these from the filtered
    # TREND in the browser (ui/src/utils/scoreFiltering.js), not from these
    # dimensions -- a Python-recomputed value here could contradict the
    # number on screen, which is the exact divergence issue #883 reported.
    assert "overallGrade" not in overview["summary"]
    assert "numericAverage" not in overview["summary"]
    assert overview["summary"]["note"]
    # Counts are exact even under filtering, so they're recomputed rather
    # than dropped: only security (2 violations) + reliability (1) survive.
    assert overview["summary"]["totalViolations"] == 3
    assert overview["summary"]["dimensionCount"] == 2
    assert overview["summary"]["severity"] == {"critical": 1, "major": 1, "minor": 1}


def test_hidden_standard_is_reachable_when_named(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    save_visible_standard_ids(repo_root, ["security", "reliability"])

    registry = _build_registry(tmp_path, repo_root, monkeypatch)

    detail_out = registry.dispatch("get_standard", {"standard_id": "clean-architecture"})
    assert detail_out["ok"], detail_out
    assert detail_out["result"]["id"] == "clean-architecture"

    violations_out = registry.dispatch("get_violations", {"dimension": "clean-architecture"})
    assert violations_out["ok"], violations_out
    assert violations_out["result"]["dimension"] == "clean-architecture"
    assert violations_out["result"]["count"] == 1
    # Naming it explicitly is the escape hatch: it is not reported as hidden
    # in a payload where it was the very thing asked for.
    assert violations_out["result"]["hiddenStandardIds"] == []
