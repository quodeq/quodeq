"""Assistant read tools against the accumulated scope, plus standards visibility."""
import json

import pytest

from quodeq.assistant.tools import ToolContext, build_registry
from quodeq.data.sqlite.assistant_repository import AssistantRepository

from ._tools_read_helpers import _acc_ctx


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


def test_unknown_dimension_messages_share_one_prefix(acc_ctx):
    registry = build_registry(acc_ctx)
    report_error = registry.dispatch("get_report", {"dimension": "nope"})["error"]
    violations_error = registry.dispatch("get_violations", {"dimension": "nope"})["error"]
    assert report_error.startswith("no report for dimension: nope. Available: ")
    assert violations_error == report_error + ". Or try get_overview for accumulated scores."
