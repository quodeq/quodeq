"""update_actions replays only appended events, under a single connection."""
import json
import uuid
from quodeq.data.projection.engine import ProjectionEngine
from quodeq.data.sqlite.state_store import SQLiteStateStore


def _write_event(project_dir, event_type, req, file="a.kt", line=1):
    # event_id must parse as a UUID (BaseEvent.event_id: UUID); a non-UUID
    # value fails pydantic validation and read_action_events silently skips
    # the line, which would make every test pass/fail for the wrong reason.
    line_obj = {
        "event_id": str(uuid.uuid4()),
        "timestamp": "2026-07-24T10:00:00Z",
        "event_type": event_type,
        "payload": {"req": req, "file": file, "line": line, "reason": None},
    }
    with open(project_dir / "actions.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(line_obj) + "\n")


def _seed_finding(run_dir, req="R-1", file="a.kt", line=1):
    # Insert one violation row the dismiss event will match.
    from quodeq.data.sqlite.connection import open_evaluation_db
    with open_evaluation_db(run_dir) as conn:
        conn.execute(
            "INSERT INTO findings (practice_id, dimension, requirement, verdict,"
            " severity, file, line, dedup_key)"
            " VALUES ('P', 'maintainability', ?, 'violation', 'major', ?, ?, ?)",
            (req, file, line, f"{req}|{file}|{line}"),
        )
        conn.commit()


def _verdict(run_dir, req):
    from quodeq.data.sqlite.connection import open_evaluation_db
    with open_evaluation_db(run_dir) as conn:
        row = conn.execute(
            "SELECT verdict FROM findings WHERE requirement = ?", (req,)
        ).fetchone()
    return row[0]


def test_second_call_replays_only_the_tail(tmp_path):
    project = tmp_path
    run_dir = project / "run1"
    run_dir.mkdir()
    _seed_finding(run_dir, "R-1")
    _seed_finding(run_dir, "R-2", line=2)

    log = project / "actions.jsonl"
    _write_event(project, "FINDING_DISMISSED", "R-1")
    engine = ProjectionEngine()
    assert engine.update_actions(log, run_dir) == 1
    assert _verdict(run_dir, "R-1") == "dismissed"

    _write_event(project, "FINDING_DISMISSED", "R-2", line=2)
    applied = engine.update_actions(log, run_dir)
    assert applied == 1          # only the appended event, not both
    assert _verdict(run_dir, "R-2") == "dismissed"
    assert _verdict(run_dir, "R-1") == "dismissed"  # earlier state intact


def test_force_replays_everything(tmp_path):
    project = tmp_path
    run_dir = project / "run1"
    run_dir.mkdir()
    _seed_finding(run_dir, "R-1")
    log = project / "actions.jsonl"
    _write_event(project, "FINDING_DISMISSED", "R-1")
    engine = ProjectionEngine()
    engine.update_actions(log, run_dir)
    assert engine.update_actions(log, run_dir, force=True) == 1  # full replay


def test_shrunk_log_triggers_full_replay(tmp_path):
    project = tmp_path
    run_dir = project / "run1"
    run_dir.mkdir()
    _seed_finding(run_dir, "R-1")
    log = project / "actions.jsonl"
    _write_event(project, "FINDING_DISMISSED", "R-1")
    _write_event(project, "FINDING_UNDISMISSED", "R-1")
    engine = ProjectionEngine()
    assert engine.update_actions(log, run_dir) == 2
    assert _verdict(run_dir, "R-1") == "violation"
    # Rewrite the log smaller (e.g. a migration compacted it).
    log.write_text(log.read_text().splitlines(keepends=True)[0])
    assert engine.update_actions(log, run_dir) == 1  # full replay of new content
    assert _verdict(run_dir, "R-1") == "dismissed"


def test_replay_uses_single_connection(tmp_path, monkeypatch):
    project = tmp_path
    run_dir = project / "run1"
    run_dir.mkdir()
    _seed_finding(run_dir, "R-1")
    log = project / "actions.jsonl"
    for i in range(20):
        _write_event(project, "FINDING_DISMISSED", "R-1")
    opens = []
    import quodeq.data.sqlite.state_store as ss
    real_open = ss.open_evaluation_db
    monkeypatch.setattr(
        ss, "open_evaluation_db",
        lambda run_dir: (opens.append(1), real_open(run_dir))[1],
    )
    ProjectionEngine().update_actions(log, run_dir)
    assert len(opens) <= 2  # one held connection (+ tolerance), not one per event
