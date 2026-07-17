"""Verify the MCP findings server wires EventLogWriter into FindingsRouter."""
import io
from pathlib import Path

from quodeq.analysis.mcp.findings_server import _build_router
from quodeq.analysis.mcp.enricher import CompiledContext
from quodeq.analysis.mcp.args import ServerArgs
from quodeq.core.events.models import EventType
from quodeq.core.events.reader import EventLogReader


def test_build_router_wires_event_log_with_run_dir(tmp_path: Path):
    findings_path = tmp_path / "run-1" / "evidence" / "timeliness_evidence.jsonl"
    findings_path.parent.mkdir(parents=True)
    findings_fh = io.StringIO()
    ctx = CompiledContext()

    router = _build_router(findings_fh, findings_path, ctx, ServerArgs())

    assert router._event_log is not None
    # The event log should write to run_dir/events.jsonl
    assert router._event_log.log_path == tmp_path / "run-1" / "events.jsonl"


def test_build_router_loads_precedent_fingerprints_from_project_dir(tmp_path: Path):
    from quodeq.context.precedent import fingerprint
    from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
    from quodeq.core.events.writer import EventLogWriter
    from quodeq.data.projection.projector import Projector
    from quodeq.services.dismissed import dismiss_finding

    # The project layout expected by _build_router:
    # project_dir/<run_id>/ -- for dismissed_keys / load_precedent_fingerprints
    # project_dir/<run_name>/evidence/<dim>_evidence.jsonl -- for the MCP server path
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    # Seed a finding in a named run under project_dir/ so SQL has a dismissed row.
    run_dir = project_dir / "r1"
    run_dir.mkdir(parents=True)
    log = run_dir / "events.jsonl"
    EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Security",
        file="auth.py", line=1, reason="r", req="S-CON-1", snippet="password = 'secret'",
    )))
    dismiss_finding(project_dir, {"req": "S-CON-1", "file": "auth.py", "line": 1})
    Projector().ensure_projected(log, run_dir, project_dir=project_dir)

    # The MCP server path: <project_dir>/<scan_run>/evidence/<dim>_evidence.jsonl
    # _build_router resolves project_dir = findings_path.parent.parent.parent
    findings_path = project_dir / "run-1" / "evidence" / "security_evidence.jsonl"
    findings_path.parent.mkdir(parents=True)

    router = _build_router(io.StringIO(), findings_path, CompiledContext(), ServerArgs())

    assert fingerprint("S-CON-1", "password = 'secret'") in router._enricher._precedent_fingerprints


def test_build_router_sets_corpus_none_when_flag_off(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("QUODEQ_SEMANTIC_PRECEDENTS", raising=False)

    findings_path = tmp_path / "run-1" / "evidence" / "security_evidence.jsonl"
    findings_path.parent.mkdir(parents=True)
    ctx = CompiledContext()

    _build_router(io.StringIO(), findings_path, ctx, ServerArgs())

    assert ctx.precedent_corpus is None


def test_build_router_degrades_when_flag_on_but_no_embedder(tmp_path: Path, monkeypatch):
    from quodeq.llm_bridge._embeddings import reset_embedding_availability_cache

    reset_embedding_availability_cache()
    monkeypatch.setenv("QUODEQ_SEMANTIC_PRECEDENTS", "1")
    monkeypatch.setenv("QUODEQ_EMBEDDING_BASE_URL", "http://127.0.0.1:1")  # nothing listens

    findings_path = tmp_path / "run-1" / "evidence" / "security_evidence.jsonl"
    findings_path.parent.mkdir(parents=True)
    ctx = CompiledContext()

    _build_router(io.StringIO(), findings_path, ctx, ServerArgs())

    assert ctx.precedent_corpus is None


def test_build_router_wires_load_precedent_corpus_with_project_and_run_dir(
    tmp_path: Path, monkeypatch,
):
    """Proves `_build_router` actually calls load_precedent_corpus with the
    resolved (project_dir, run_dir) and stores its return value -- the
    None-when-flag-off tests above pass trivially against the field default,
    so this closes that gap."""
    import quodeq.analysis.mcp.findings_server as findings_server_module

    sentinel = object()
    calls = []

    def fake_load_precedent_corpus(project_dir, run_dir):
        calls.append((project_dir, run_dir))
        return sentinel

    monkeypatch.setattr(
        findings_server_module, "load_precedent_corpus", fake_load_precedent_corpus,
    )

    project_dir = tmp_path / "project"
    findings_path = project_dir / "run-1" / "evidence" / "security_evidence.jsonl"
    findings_path.parent.mkdir(parents=True)
    ctx = CompiledContext()

    _build_router(io.StringIO(), findings_path, ctx, ServerArgs())

    assert calls == [(project_dir, project_dir / "run-1")]
    assert ctx.precedent_corpus is sentinel


def test_build_router_emits_findings_to_jsonl_and_event_log(tmp_path: Path):
    findings_path = tmp_path / "run-1" / "evidence" / "timeliness_evidence.jsonl"
    findings_path.parent.mkdir(parents=True)
    fh = io.StringIO()
    router = _build_router(fh, findings_path, CompiledContext(), ServerArgs())

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
