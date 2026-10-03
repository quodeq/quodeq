"""The live path places every finding through admission."""
from __future__ import annotations

import io
import json

from quodeq.analysis.mcp.enricher import CompiledContext
from quodeq.analysis.mcp.handlers import handle_tools_call
from quodeq.analysis.mcp.receipt import ReceiptStatus
from quodeq.analysis.mcp.router import FindingsRouter
from quodeq.core.admission import StandardCatalog, StandardIndex

_ACC = StandardIndex("accessibility", {"ACC-PER-01": "Perceivable", "ACC-PER-02": "Perceivable",
                                       "ACC-OPR-04": "Operable"})
_SEC = StandardIndex("security", {"S-CON-1": "Confidentiality"})


class _Events:
    def __init__(self) -> None:
        self.emitted: list = []

    def emit(self, event) -> None:
        self.emitted.append(event)


def _router(events: _Events | None = None) -> tuple[FindingsRouter, io.StringIO]:
    fh = io.StringIO()
    ctx = CompiledContext(dimension="accessibility", catalog=StandardCatalog.of([_ACC, _SEC]))
    return FindingsRouter(fh, ctx, file_reader=lambda _p: "", event_log=events), fh


def _args(**over) -> dict:
    return {"req": "ACC-PER-01", "t": "violation", "d": "accessibility", "file": "a.kt",
            "line": 3, "severity": "major", "w": "w", "reason": "r", **over}


def _rows(fh: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in fh.getvalue().splitlines()]


def test_a_known_code_is_recorded_with_the_standards_principle() -> None:
    router, fh = _router()

    receipt = router.receive(_args(p="Operable"))

    assert receipt.status is ReceiptStatus.RECORDED
    (row,) = _rows(fh)
    assert (row["req"], row["p"], row["d"]) == ("ACC-PER-01", "Perceivable", "accessibility")


def test_a_near_miss_is_recorded_under_the_canonical_code() -> None:
    router, fh = _router()

    router.receive(_args(req="acc-per-1"))

    (row,) = _rows(fh)
    assert (row["req"], row["req_reported"], row["p"]) == ("ACC-PER-01", "acc-per-1", "Perceivable")


def test_an_unknown_code_is_refused_once_with_the_nearest_ids() -> None:
    events = _Events()
    router, fh = _router(events)

    first = router.receive(_args(req="ACC-PER-09"))

    assert first.status is ReceiptStatus.REJECTED and first.is_error
    assert "ACC-PER-02" in first.message
    assert _rows(fh) == [] and events.emitted == []


def test_a_second_unknown_code_is_kept_as_unmapped_without_an_event() -> None:
    events = _Events()
    router, fh = _router(events)
    router.receive(_args(req="ACC-PER-09"))

    second = router.receive(_args(req="ACC-PER-09"))

    assert second.status is ReceiptStatus.UNMAPPED
    (row,) = _rows(fh)
    assert row["admission"] == "unmapped" and row["unmapped_reason"] == "unknown_requirement"
    assert "p" not in row
    assert events.emitted == []


def test_a_retry_with_a_valid_code_is_recorded() -> None:
    router, fh = _router()
    router.receive(_args(req="ACC-PER-09"))

    retry = router.receive(_args(req="ACC-PER-02"))

    assert retry.status is ReceiptStatus.RECORDED
    assert [r["req"] for r in _rows(fh)] == ["ACC-PER-02"]


def test_a_code_of_another_scanned_dimension_is_routed_there() -> None:
    router, fh = _router()

    router.receive(_args(req="S-CON-1"))

    (row,) = _rows(fh)
    assert (row["d"], row["p"]) == ("security", "Confidentiality")


def test_the_mcp_tool_reports_a_refusal_as_a_failed_call() -> None:
    router, _fh = _router()

    reply = handle_tools_call(
        request_id=7, params={"name": "report_finding", "arguments": _args(req="NOPE-1")}, router=router)

    assert reply["result"]["isError"] is True


def test_an_unknown_code_with_a_valid_principle_is_refused_then_kept_under_it() -> None:
    events = _Events()
    router, fh = _router(events)

    first = router.receive(_args(req="ACC-PER-99", p="Operable"))
    second = router.receive(_args(req="ACC-PER-99", p="Operable"))

    assert first.status is ReceiptStatus.REJECTED
    assert second.status is ReceiptStatus.RECORDED
    (row,) = _rows(fh)
    assert (row["p"], row["req_unknown"]) == ("Operable", True)
    assert len(events.emitted) == 1


def test_two_requirements_of_one_principle_on_a_line_are_two_findings(tmp_path) -> None:
    from quodeq.analysis.subagents.jsonl_utils import deduplicate_jsonl

    router, fh = _router()
    router.receive(_args(req="ACC-PER-01"))
    router.receive(_args(req="ACC-PER-02"))
    duplicate = router.receive(_args(req="acc-per-2"))

    assert duplicate.status is ReceiptStatus.DUPLICATE
    jsonl = tmp_path / "e.jsonl"
    jsonl.write_text(fh.getvalue() * 2, encoding="utf-8")
    assert deduplicate_jsonl(jsonl) == 2
