"""verify_finding/unverify_finding accept an injected ActionLog writer,
mirroring services/deleted.py's delete_finding(..., writer=)."""
from __future__ import annotations

from quodeq.core.events.models import FindingUnverifiedEvent, FindingVerifiedEvent
from quodeq.services.verified import unverify_finding, verify_finding


class _FakeWriter:
    """Fake ActionLog: records emitted events, touches no disk."""

    def __init__(self) -> None:
        self.emitted: list = []

    def emit(self, event) -> None:
        self.emitted.append(event)


def test_verify_finding_with_fake_writer_emits_no_disk_write(tmp_path):
    fake = _FakeWriter()
    project_dir = tmp_path / "does-not-exist"

    verify_finding(
        project_dir,
        {"req": "r1", "file": "a.py", "line": 3, "note": "checked the guard"},
        writer=fake,
    )

    assert not project_dir.exists()
    assert len(fake.emitted) == 1
    event = fake.emitted[0]
    assert isinstance(event, FindingVerifiedEvent)
    assert event.payload.req == "r1"
    assert event.payload.file == "a.py"
    assert event.payload.line == 3
    assert event.payload.note == "checked the guard"


def test_unverify_finding_with_fake_writer_emits_no_disk_write(tmp_path):
    fake = _FakeWriter()
    project_dir = tmp_path / "does-not-exist"

    unverify_finding(project_dir, {"req": "r1", "file": "a.py", "line": 3}, writer=fake)

    assert not project_dir.exists()
    assert len(fake.emitted) == 1
    event = fake.emitted[0]
    assert isinstance(event, FindingUnverifiedEvent)
    assert event.payload.req == "r1"
    assert event.payload.file == "a.py"
    assert event.payload.line == 3


def test_verify_finding_default_path_still_writes_to_disk(tmp_path):
    """No writer passed -- default path is unchanged (ActionLogWriter on disk)."""
    verify_finding(tmp_path, {"req": "r1", "file": "a.py", "line": 3, "note": "n"})
    assert (tmp_path / "actions.jsonl").exists()
