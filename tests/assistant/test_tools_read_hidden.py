"""Hidden-standard filtering in get_scores and get_violations, both scopes."""
import json

from ._tools_read_helpers import _acc_ctx, _run_ctx


# --- visible_only: a blank/missing dimension is always visible (Finding 2). -


def test_visible_only_blank_dimension_kept_and_not_named_hidden(tmp_path):
    from quodeq.assistant.tools._read_tools import visible_only
    ctx = _run_ctx(tmp_path, visible_standard_ids=("security",))
    kept, hidden = visible_only(ctx, [{"dimension": "security"}, {"nodim": 1}])
    assert kept == [{"dimension": "security"}, {"nodim": 1}]
    assert hidden == []


def test_visible_only_blank_dimension_kept_alongside_a_real_hidden_one(tmp_path):
    from quodeq.assistant.tools._read_tools import visible_only
    ctx = _run_ctx(tmp_path, visible_standard_ids=("security",))
    kept, hidden = visible_only(ctx, [
        {"dimension": "reliability"}, {"nodim": 1}, {"dimension": "security"},
    ])
    assert kept == [{"nodim": 1}, {"dimension": "security"}]
    assert hidden == ["reliability"]
    assert "" not in hidden


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


def test_get_scores_filename_fallback_kept_when_stem_is_visible(tmp_path):
    """A stem-derived dimension name matched against an ACTIVE selection that
    includes it: kept, and never named in hiddenStandardIds."""
    from quodeq.assistant.tools._read_tools import _get_scores
    ctx = _run_ctx(tmp_path, visible_standard_ids=("security", "no-dim-field"))
    eval_dir = ctx.run_dir / "evaluation"
    (eval_dir / "no-dim-field.json").write_text(json.dumps({
        "overallScore": 42, "overallGrade": "D", "violations": [],
    }))
    out = _get_scores(ctx)
    assert out["scores"]["no-dim-field"] == {"score": 42, "grade": "D"}
    assert "no-dim-field" not in out["hiddenStandardIds"]


def test_get_scores_filename_fallback_hidden_when_stem_not_visible(tmp_path):
    """The same stem-derived name against an ACTIVE selection that excludes
    it: dropped, and named in hiddenStandardIds like any other dimension."""
    from quodeq.assistant.tools._read_tools import _get_scores
    ctx = _run_ctx(tmp_path, visible_standard_ids=("security",))
    eval_dir = ctx.run_dir / "evaluation"
    (eval_dir / "no-dim-field.json").write_text(json.dumps({
        "overallScore": 42, "overallGrade": "D", "violations": [],
    }))
    out = _get_scores(ctx)
    assert "no-dim-field" not in out["scores"]
    assert "no-dim-field" in out["hiddenStandardIds"]


def test_get_violations_filename_fallback_kept_when_stem_is_visible(tmp_path):
    """Covers `_violations_from_run`'s use of `_raw_run_dims` (the second call
    site the helper exists for) against an ACTIVE selection that includes the
    stem-derived name."""
    from quodeq.assistant.tools._read_tools import get_violations
    ctx = _run_ctx(tmp_path, visible_standard_ids=("security", "no-dim-field"))
    eval_dir = ctx.run_dir / "evaluation"
    (eval_dir / "no-dim-field.json").write_text(json.dumps({
        "overallScore": 42, "overallGrade": "D",
        "violations": [{"principle": "X1", "file": "f.py", "line": 1,
                         "severity": "minor", "title": "t", "reason": "r"}],
    }))
    out = get_violations(ctx)
    assert out["by_principle"].get("X1") == 1
    assert "no-dim-field" not in out["hiddenStandardIds"]


def test_get_violations_filename_fallback_hidden_when_stem_not_visible(tmp_path):
    """Same call site, ACTIVE selection that excludes the stem-derived name."""
    from quodeq.assistant.tools._read_tools import get_violations
    ctx = _run_ctx(tmp_path, visible_standard_ids=("security",))
    eval_dir = ctx.run_dir / "evaluation"
    (eval_dir / "no-dim-field.json").write_text(json.dumps({
        "overallScore": 42, "overallGrade": "D",
        "violations": [{"principle": "X1", "file": "f.py", "line": 1,
                         "severity": "minor", "title": "t", "reason": "r"}],
    }))
    out = get_violations(ctx)
    assert "X1" not in out["by_principle"]
    assert "no-dim-field" in out["hiddenStandardIds"]


def test_get_violations_excludes_hidden_dimensions_run_scope(tmp_path):
    from quodeq.assistant.tools._read_tools import get_violations
    ctx = _run_ctx(tmp_path, visible_standard_ids=("security",))
    out = get_violations(ctx)
    # reliability's R1 is excluded; only security's P1/P2 counts remain.
    assert out["by_principle"] == {"P1": 2, "P2": 1}
    assert out["hiddenStandardIds"] == ["reliability"]


def test_get_violations_named_hidden_dimension_still_works_run_scope(tmp_path):
    """Explicitly naming a hidden dimension is the deliberate escape hatch."""
    from quodeq.assistant.tools._read_tools import get_violations
    ctx = _run_ctx(tmp_path, visible_standard_ids=("security",))
    out = get_violations(ctx, dimension="reliability")
    assert out["dimension"] == "reliability"
    assert out["count"] == 1
    assert out["hiddenStandardIds"] == []


def test_get_violations_excludes_hidden_dimensions_accumulated(tmp_path, monkeypatch):
    from quodeq.assistant.tools._read_tools import get_violations
    ctx = _acc_ctx(tmp_path, monkeypatch, visible_standard_ids=("security",))
    out = get_violations(ctx)
    assert out["by_principle"] == {"S1": 1, "S2": 1}
    assert out["hiddenStandardIds"] == ["reliability"]


def test_get_violations_named_hidden_dimension_still_works_accumulated(tmp_path, monkeypatch):
    from quodeq.assistant.tools._read_tools import get_violations
    ctx = _acc_ctx(tmp_path, monkeypatch, visible_standard_ids=("security",))
    out = get_violations(ctx, dimension="reliability")
    assert out["dimension"] == "reliability"
    assert out["count"] > 0
    assert out["hiddenStandardIds"] == []
