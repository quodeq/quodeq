"""Hidden-standard filtering in search_findings and not-found error messages."""
import pytest

from quodeq.assistant.tools import ToolError

from ._tools_read_helpers import _acc_ctx, _finding, _run_ctx


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


def test_search_findings_visible_rows_survive_hidden_rows_ahead_of_limit(tmp_path):
    """Reviewer-proven regression: 25 matching hidden-dimension rows inserted
    BEFORE 3 matching visible rows, with a limit smaller than the hidden
    count. SQL orders by insertion order (id), so filtering the returned rows
    AFTER `ORDER BY id LIMIT ?` can return zero results even though visible
    matches exist -- the hidden rows alone fill the whole limit window.
    The fix pushes the exclusion into the query itself, before LIMIT."""
    from quodeq.assistant.tools._read_tools import _search_findings
    hidden_rows = [
        _finding(d="reliability", p=f"rel-{i}", req=f"rel-{i}",
                 file=f"src/rel{i}.py", line=i, reason="widget flaky")
        for i in range(25)
    ]
    visible_rows = [
        _finding(d="security", p=f"sec-{i}", req=f"sec-{i}",
                 file=f"src/sec{i}.py", line=i, reason="widget insecure")
        for i in range(3)
    ]
    ctx = _run_ctx(tmp_path, visible_standard_ids=("security",),
                    findings=hidden_rows + visible_rows)
    out = _search_findings(ctx, query="widget", limit=20)
    assert len(out["findings"]) == 3
    assert {f["dimension"] for f in out["findings"]} == {"security"}
    assert out["hiddenStandardIds"] == ["reliability"]


def test_search_findings_hidden_dim_reported_even_with_zero_matching_hits(tmp_path):
    """hiddenStandardIds must reflect what was withheld even when every one of
    a hidden dimension's rows is excluded from the SQL result (the source can
    no longer be "the rows the query returned")."""
    from quodeq.assistant.tools._read_tools import _search_findings
    hidden_rows = [
        _finding(d="reliability", p=f"rel-{i}", req=f"rel-{i}",
                 file=f"src/rel{i}.py", line=i, reason="widget flaky")
        for i in range(5)
    ]
    ctx = _run_ctx(tmp_path, visible_standard_ids=("security",),
                    findings=hidden_rows + [_finding()])
    out = _search_findings(ctx, query="widget", limit=1)
    assert out["findings"] == []
    assert out["hiddenStandardIds"] == ["reliability"]


def test_search_findings_blank_dimension_finding_always_returned(tmp_path):
    """A blank/missing dimension is always visible and must never itself
    surface in hiddenStandardIds (Finding 2)."""
    from quodeq.assistant.tools._read_tools import _search_findings
    findings = [
        _finding(d="reliability", p="req-2", req="req-2", file="src/r.py",
                 reason="widget risk"),
        _finding(d="", p="req-3", req="req-3", file="src/blank.py",
                 reason="widget risk"),
    ]
    ctx = _run_ctx(tmp_path, visible_standard_ids=("security",), findings=findings)
    out = _search_findings(ctx, query="widget")
    assert {f["file"] for f in out["findings"]} == {"src/blank.py"}
    assert out["hiddenStandardIds"] == ["reliability"]
    assert "" not in out["hiddenStandardIds"]


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
