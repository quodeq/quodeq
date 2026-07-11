from quodeq_bench.evidence import Finding
from quodeq_bench.matcher import CaseMatch, match_case, normalize_path
from quodeq_bench.models import CaseTruth, Label


def _finding(**overrides) -> Finding:
    base = dict(
        dimension="security",
        file="app.py",
        line=13,
        severity="critical",
        req="S-CON-1",
        vt="sql-injection",
        refs=("CWE-89",),
        title="SQLi",
    )
    base.update(overrides)
    return Finding(**base)


def _truth(labels: tuple[Label, ...], exhaustive: bool = True) -> CaseTruth:
    return CaseTruth(
        case_id="case",
        language="python",
        exhaustive=exhaustive,
        clean_files=(),
        labels=labels,
    )


_SQLI = Label(
    file="app.py", line=13, dimension="security", severity="critical",
    note="sqli", cwes=(89, 564), reqs=(),
)


def test_normalize_path() -> None:
    assert normalize_path("./src\\app.py") == "src/app.py"


def test_exact_match_by_cwe() -> None:
    result = match_case(_truth((_SQLI,)), [_finding()])
    assert result["security"] == CaseMatch(
        total_labels=1, matched_labels=1, matched_findings=1,
        fp_findings=0, duplicates=0, severity_agreements=1,
    )


def test_match_within_line_window_and_req() -> None:
    label = Label(
        file="orders.py", line=40, dimension="maintainability",
        severity="major", note="god fn", cwes=(), reqs=("M-MOD-1",),
    )
    finding = _finding(
        dimension="maintainability", file="orders.py", line=44,
        severity="minor", req="M-MOD-1", refs=(),
    )
    result = match_case(_truth((label,)), [finding])
    assert result["maintainability"].matched_labels == 1
    assert result["maintainability"].severity_agreements == 0


def test_no_match_outside_window() -> None:
    result = match_case(_truth((_SQLI,)), [_finding(line=25)])
    assert result["security"].matched_labels == 0
    assert result["security"].fp_findings == 1


def test_wrong_class_is_fp_when_exhaustive() -> None:
    result = match_case(_truth((_SQLI,)), [_finding(refs=("CWE-798",), req="X-1")])
    assert result["security"].matched_labels == 0
    assert result["security"].fp_findings == 1


def test_unmatched_ignored_when_not_exhaustive() -> None:
    result = match_case(_truth((_SQLI,), exhaustive=False), [_finding(line=99)])
    assert result["security"].fp_findings == 0


def test_duplicate_findings_count_once() -> None:
    result = match_case(_truth((_SQLI,)), [_finding(), _finding(line=14)])
    assert result["security"].matched_labels == 1
    assert result["security"].matched_findings == 2
    assert result["security"].duplicates == 1


def test_span_label_overlap() -> None:
    label = Label(
        file="cfg.py", line=1, end_line=3, dimension="security",
        severity="major", note="secrets", cwes=(798,), reqs=(),
    )
    finding = _finding(file="cfg.py", line=2, refs=("CWE-798",), severity="major")
    result = match_case(_truth((label,)), [finding])
    assert result["security"].matched_labels == 1
