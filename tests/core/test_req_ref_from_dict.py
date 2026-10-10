"""ReqRef.from_dict: stored refs keep a label whichever shape they were written in."""
from __future__ import annotations

import json

from quodeq.core.evidence.jsonl import parse_jsonl_line
from quodeq.core.types.req_ref import ReqRef

_CWE = {"source": "cwe", "id": "1080", "name": "Excessive lines", "url": "https://cwe.mitre.org/data/definitions/1080.html"}
_CISQ = {"source": "cisq", "id": None, "name": "Line limits", "url": "https://www.it-cisq.org/coding-rules/"}


def test_a_labelled_ref_keeps_its_label() -> None:
    assert ReqRef.from_dict({"label": "ERR08-J", "url": "https://x"}) == ReqRef("ERR08-J", "https://x")


def test_a_standard_shaped_ref_gets_a_label_from_source_and_id() -> None:
    assert ReqRef.from_dict(_CWE).label == "CWE-1080"
    assert ReqRef.from_dict(_CISQ).label == "CISQ"


def test_a_ref_with_nothing_to_name_it_stays_unlabelled() -> None:
    assert ReqRef.from_dict({"url": "https://example.com/x"}) == ReqRef("", "https://example.com/x")


def test_evidence_written_since_admission_reads_back_labelled() -> None:
    row = {"p": "Analyzability", "t": "violation", "d": "maintainability", "req": "M-ANA-1", "req_refs": [_CWE, _CISQ]}
    judgment, _ = parse_jsonl_line(json.dumps(row))
    assert [r.label for r in judgment.req_refs] == ["CWE-1080", "CISQ"]


def test_a_report_that_kept_only_the_url_is_labelled_from_it() -> None:
    def label(url: str) -> str:
        return ReqRef.from_dict({"label": "", "url": url}).label
    assert label("https://cwe.mitre.org/data/definitions/1080.html") == "CWE-1080"
    assert label("https://www.it-cisq.org/coding-rules/") == "CISQ"
    assert label("https://wiki.sei.cmu.edu/confluence/display/java/ERR08-J.+Do+not+catch+NullPointerException") == "ERR08-J"
    assert label("https://owasp.org/www-project-application-security-verification-standard/") == "ASVS"
    assert label("https://example.com/unknown") == ""
