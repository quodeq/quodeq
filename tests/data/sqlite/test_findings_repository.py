from pathlib import Path

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.writer import EventLogWriter
from quodeq.data.projection.projector import ProjectionResult, Projector
from quodeq.data.sqlite.connection import open_evaluation_db
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository


def _finding(p="P1", file="x.py", line=1, t="violation", **kw):
    return {"p": p, "file": file, "line": line, "t": t, "severity": "medium",
            "reason": kw.get("reason", "r"), "snippet": kw.get("snippet", "s"),
            "d": kw.get("d", "dim"), **{k: v for k, v in kw.items() if k not in {"reason","snippet","d"}}}


def test_insert_and_count_by_dimension(tmp_path: Path):
    repo = SqliteFindingsRepository(tmp_path)
    repo.insert_finding(_finding(p="P1", d="timeliness"))
    repo.insert_finding(_finding(p="P2", d="timeliness", line=2))
    repo.insert_finding(_finding(p="P3", d="security", line=3))
    counts = repo.count_by_dimension()
    assert counts == {"timeliness": 2, "security": 1}


def test_insert_finding_dedups_on_unique_key(tmp_path: Path):
    repo = SqliteFindingsRepository(tmp_path)
    inserted_first = repo.insert_finding(_finding(p="P1", file="x.py", line=1))
    inserted_second = repo.insert_finding(_finding(p="P1", file="x.py", line=1))
    assert inserted_first is True
    assert inserted_second is False  # duplicate, ignored


def test_list_by_dimension_returns_judgments(tmp_path: Path):
    repo = SqliteFindingsRepository(tmp_path)
    repo.insert_finding(_finding(p="P1", d="timeliness", reason="late"))
    repo.insert_finding(_finding(p="P2", d="security", line=99))
    items = repo.list_by_dimension("timeliness")
    assert len(items) == 1
    assert items[0].practice_id == "P1"
    assert items[0].reason == "late"


def test_search_uses_fts5(tmp_path: Path):
    repo = SqliteFindingsRepository(tmp_path)
    repo.insert_finding(_finding(p="P1", reason="missing input validation"))
    repo.insert_finding(_finding(p="P2", line=2, reason="performance regression"))
    hits = repo.search("validation")
    assert {h.practice_id for h in hits} == {"P1"}


def test_dismiss_finding_atomically(tmp_path: Path):
    repo = SqliteFindingsRepository(tmp_path)
    repo.insert_finding(_finding(p="P1"))
    changed = repo.set_verdict(practice_id="P1", file="x.py", line=1, verdict="dismissed")
    assert changed == 1
    items = repo.list_by_dimension("dim")
    assert items[0].verdict == "dismissed"


def test_search_query_with_fts_special_chars_does_not_raise(tmp_path: Path):
    """User input with FTS5 operators is treated as a phrase, not a query."""
    repo = SqliteFindingsRepository(tmp_path)
    repo.insert_finding(_finding(p="P1", reason="missing input"))
    # Each of these would raise or misbehave without sanitization.
    for query in ["foo:", "a-b", 'unbalanced"', "a OR b", "*"]:
        # Just verify no exception; result set may be empty.
        repo.search(query)


def test_search_query_finds_exact_phrase_with_punctuation(tmp_path: Path):
    repo = SqliteFindingsRepository(tmp_path)
    repo.insert_finding(_finding(p="P1", reason="error: connection refused"))
    repo.insert_finding(_finding(p="P2", line=2, reason="warning: deprecated"))
    hits = repo.search("error: connection")
    assert {h.practice_id for h in hits} == {"P1"}


def test_search_respects_limit(tmp_path: Path):
    repo = SqliteFindingsRepository(tmp_path)
    for i in range(10):
        repo.insert_finding(_finding(p=f"P{i}", line=i, reason="duplicate text"))
    hits = repo.search("duplicate", limit=3)
    assert len(hits) == 3


class _SpyProjector(Projector):
    """Projector that records ensure_projected invocations."""

    def __init__(self) -> None:
        super().__init__()
        self.ensure_calls = 0

    def ensure_projected(self, events_path, run_dir):  # type: ignore[override]
        self.ensure_calls += 1
        return ProjectionResult(events_projected=0, rebuilt=False)


def _write_event(log: Path, practice_id: str = "P1") -> None:
    writer = EventLogWriter(log)
    writer.emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id=practice_id, verdict="violation", dimension="dim",
        file="x.py", line=1, reason="r",
    )))


def test_read_triggers_ensure(tmp_path: Path):
    _write_event(tmp_path / "events.jsonl")
    spy = _SpyProjector()
    repo = SqliteFindingsRepository(tmp_path, projector=spy)

    repo.list_by_dimension("dim")
    repo.count_by_dimension()
    repo.search("r")

    assert spy.ensure_calls == 3


def test_write_does_not_trigger_ensure(tmp_path: Path):
    _write_event(tmp_path / "events.jsonl")
    spy = _SpyProjector()
    repo = SqliteFindingsRepository(tmp_path, projector=spy)

    repo.insert_finding(_finding(p="P1"))
    repo.set_verdict(practice_id="P1", file="x.py", line=1, verdict="dismissed")

    assert spy.ensure_calls == 0


def test_read_skips_ensure_when_no_event_log(tmp_path: Path):
    spy = _SpyProjector()
    repo = SqliteFindingsRepository(tmp_path, projector=spy)

    repo.count_by_dimension()

    assert spy.ensure_calls == 0
