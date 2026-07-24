"""read_action_events can resume from a byte offset (append-only log)."""
from quodeq.core.events.models import FindingDismissedEvent, FindingDismissed
from quodeq.data.actions_log import ActionLogWriter, read_action_events


def _emit(project_dir, req):
    ActionLogWriter(project_dir).emit(
        FindingDismissedEvent(
            payload=FindingDismissed(req=req, file="a.kt", line=1, reason=None)
        )
    )


def test_from_offset_skips_already_read_events(tmp_path):
    _emit(tmp_path, "R-1")
    offset = (tmp_path / "actions.jsonl").stat().st_size
    _emit(tmp_path, "R-2")
    tail = list(read_action_events(tmp_path, from_offset=offset))
    assert [e.payload.req for e in tail] == ["R-2"]


def test_default_reads_everything(tmp_path):
    _emit(tmp_path, "R-1")
    _emit(tmp_path, "R-2")
    assert len(list(read_action_events(tmp_path))) == 2


def test_offset_at_eof_yields_nothing(tmp_path):
    _emit(tmp_path, "R-1")
    size = (tmp_path / "actions.jsonl").stat().st_size
    assert list(read_action_events(tmp_path, from_offset=size)) == []
