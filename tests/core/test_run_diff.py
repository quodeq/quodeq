"""Two runs' findings classified by identity, not by count."""
from __future__ import annotations

from quodeq.core.run_diff import diff_findings, identity


def _f(req: str, file: str, line: int, snippet: str = "", severity: str = "minor",
       carried: bool = False) -> dict:
    d = {"req": req, "file": file, "line": line, "snippet": snippet, "severity": severity}
    if carried:
        d["carried_forward"] = True
    return d


def test_identity_is_req_file_fingerprint() -> None:
    a = _f("M-MDF-1", "a.py", 10, "x = 250")
    b = _f("M-MDF-1", "a.py", 99, "x = 250")   # moved within the file
    assert identity(a) == identity(b)


def test_blank_snippet_keys_on_line() -> None:
    a = _f("M-MDF-1", "a.py", 10)
    b = _f("M-MDF-1", "a.py", 11)
    assert identity(a) != identity(b)


def test_self_diff_is_all_same() -> None:
    prev = [_f("M-MDF-1", "a.py", 1, "x = 1"), _f("M-REU-1", "b.py", 2, "dup()")]
    d = diff_findings(prev, prev, current_files={"a.py", "b.py"})
    assert (len(d.same), len(d.new), len(d.resolved), d.types_closed, d.types_opened) == (
        2, 0, 0, [], [])


def test_new_resolved_and_types() -> None:
    prev = [_f("M-MDF-1", "a.py", 1, "x = 1"), _f("M-REU-1", "b.py", 2, "dup()")]
    curr = [_f("M-MDF-1", "a.py", 1, "x = 1"), _f("M-ANA-9", "a.py", 5, "long line")]
    d = diff_findings(prev, curr, current_files={"a.py", "b.py"})
    assert [x["req"] for x in d.new] == ["M-ANA-9"]
    assert [x["req"] for x in d.resolved] == ["M-REU-1"]
    assert (d.types_closed, d.types_opened) == (["M-REU-1"], ["M-ANA-9"])
    assert d.per_req == {"M-MDF-1": (1, 1), "M-REU-1": (1, 0), "M-ANA-9": (0, 1)}


def test_unseen_file_is_not_resolved() -> None:
    prev = [_f("M-REU-1", "b.py", 2, "dup()")]
    d = diff_findings(prev, [], current_files={"a.py"})
    assert (d.resolved, [x["req"] for x in d.not_reevaluated]) == ([], ["M-REU-1"])


def test_moved_across_files() -> None:
    prev = [_f("M-REU-1", "old.py", 2, "dup()")]
    curr = [_f("M-REU-1", "new.py", 7, "dup()")]
    d = diff_findings(prev, curr, current_files={"new.py"})
    assert ([x["file"] for x in d.moved], d.new, d.resolved) == (["new.py"], [], [])


def test_carried_counts_separately_and_majors_delta() -> None:
    prev = [_f("M-MOD-3", "a.py", 1, "import x", severity="major")]
    curr = [_f("M-MOD-3", "a.py", 1, "import x", severity="major", carried=True),
            _f("M-MOD-4", "c.py", 3, "cycle", severity="major")]
    d = diff_findings(prev, curr, current_files={"a.py", "c.py"})
    assert (len(d.carried), len(d.same), d.majors_delta) == (1, 0, 1)
