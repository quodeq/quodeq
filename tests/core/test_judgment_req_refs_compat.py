"""Regression: Judgment.req_refs must accept the legacy bare-string format.

Historical events.jsonl files (pre-ReqRef-struct refactor) stored req_refs as
a list of bare strings:

    {"req_refs": ["CWE-89", "CISQ", "ASVS V5.3.5"], ...}

The current Judgment model declares ``req_refs: List[ReqRef]`` and pydantic
rejects bare strings during validation. The EventLogReader then silently
skips the entire event, which means whole runs project as zero findings —
the UI shows the violations from the dimension JSON file, but the score is
computed off an empty SQL DB and renders 10.0 grade A regardless of how
many violations exist.

The fix coerces bare strings to ``ReqRef(label=<string>, url="")`` so old
events round-trip cleanly through the reader. This pins that contract.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.events.models import JudgmentCreatedEvent
from quodeq.core.events.reader import EventLogReader


_LEGACY_EVENT_JSON = {
    "event_id": "00000000-0000-0000-0000-000000000001",
    "timestamp": "2026-05-17T19:20:00+00:00",
    "event_type": "JUDGMENT_CREATED",
    "payload": {
        "practice_id": "Integrity",
        "verdict": "violation",
        "dimension": "security",
        "file": "auth.py",
        "line": 10,
        "reason": "Use of weak cryptographic hash (MD5)",
        "severity": "major",
        "req": "Integrity.MD5",
        # Legacy format: bare strings rather than {label, url} dicts.
        "req_refs": ["CWE-327", "CISQ"],
    },
}


def test_judgment_model_accepts_bare_string_req_refs() -> None:
    """Judgment validation must coerce ['CWE-327', 'CISQ'] to ReqRef objects."""
    event = JudgmentCreatedEvent.model_validate(_LEGACY_EVENT_JSON)
    refs = event.payload.req_refs
    assert len(refs) == 2, f"Expected 2 ReqRefs, got {refs}"
    labels = [r.label for r in refs]
    assert labels == ["CWE-327", "CISQ"], (
        f"Bare-string req_refs not coerced into ReqRef.label. Got: {labels}"
    )
    # url defaults to empty for the legacy format; the references are kept
    # so the UI's filterValidRefs() drops them gracefully (it requires url
    # to start with http(s)://).
    urls = [r.url for r in refs]
    assert urls == ["", ""], f"Expected empty urls, got: {urls}"


def test_event_log_reader_does_not_drop_legacy_req_refs(tmp_path: Path) -> None:
    """End-to-end: a JSONL file of legacy events must project every event,
    not silently skip them on ValidationError."""
    log_path = tmp_path / "events.jsonl"
    with log_path.open("w") as f:
        for i in range(5):
            ev = json.loads(json.dumps(_LEGACY_EVENT_JSON))
            ev["event_id"] = f"00000000-0000-0000-0000-00000000000{i + 1}"
            ev["payload"]["line"] = 10 + i
            f.write(json.dumps(ev) + "\n")

    reader = EventLogReader(log_path)
    events = list(reader.stream())

    assert len(events) == 5, (
        f"EventLogReader dropped {5 - len(events)} legacy events on ValidationError. "
        f"This silently corrupts every old run — projection produces an empty DB "
        f"and the scoring engine returns 10.0 / Exemplary while the UI lists real "
        f"violations from the dimension JSON file."
    )
