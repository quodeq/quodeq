"""Verify the MCP findings server wires EventLogWriter into FindingsRouter."""
import io
from pathlib import Path

from quodeq.analysis.mcp.findings_server import _build_router
from quodeq.analysis.mcp.enricher import CompiledContext
from quodeq.core.events.models import EventType
from quodeq.core.events.reader import EventLogReader


def test_build_router_wires_event_log_with_run_dir(tmp_path: Path):
    findings_path = tmp_path / "run-1" / "evidence" / "timeliness_evidence.jsonl"
    findings_path.parent.mkdir(parents=True)
    findings_fh = io.StringIO()
    ctx = CompiledContext()

    router = _build_router(findings_fh, findings_path, ctx)

    assert router._event_log is not None
    # The event log should write to run_dir/events.jsonl
    assert router._event_log.log_path == tmp_path / "run-1" / "events.jsonl"


def test_build_router_loads_precedent_fingerprints_from_project_dir(tmp_path: Path):
    import json

    from quodeq.context.precedent import fingerprint

    project_dir = tmp_path
    findings_path = project_dir / "run-1" / "evidence" / "security_evidence.jsonl"
    findings_path.parent.mkdir(parents=True)
    (project_dir / "dismissed.json").write_text(json.dumps([
        {"req": "S-CON-1", "snippet": "password = 'secret'"},
    ]))

    router = _build_router(io.StringIO(), findings_path, CompiledContext())

    assert fingerprint("S-CON-1", "password = 'secret'") in router._enricher._precedent_fingerprints


def test_build_router_emits_findings_to_jsonl_and_event_log(tmp_path: Path):
    findings_path = tmp_path / "run-1" / "evidence" / "timeliness_evidence.jsonl"
    findings_path.parent.mkdir(parents=True)
    fh = io.StringIO()
    router = _build_router(fh, findings_path, CompiledContext())

    msg, dup = router.receive({
        "p": "P1", "file": "x.py", "line": 1, "t": "violation",
        "severity": "medium", "d": "dim", "reason": "r", "snippet": "s",
        "w": "title",
    })

    assert dup is False
    assert fh.getvalue().count("\n") == 1
    events_log = tmp_path / "run-1" / "events.jsonl"
    assert events_log.exists()
    events = EventLogReader(events_log).read_all()
    assert len(events) == 1
    assert events[0].event_type == EventType.JUDGMENT_CREATED
