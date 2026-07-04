"""Persistent 'verified' badges for findings, project-level actions.jsonl.

Mirrors services/dismissed.py: verify_finding()/unverify_finding() append
events; verified_entries() replays the log into the net set. Badges never
affect scores; they record that a human approved the assistant's
real-defect verdict for a finding keyed by (req, file, line).
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.events.models import (
    EventType,
    FindingUnverified,
    FindingUnverifiedEvent,
    FindingVerified,
    FindingVerifiedEvent,
)
from quodeq.data.actions_log import ActionLogWriter, read_action_events


def verify_finding(project_dir: Path, finding: dict) -> None:
    """Append a FindingVerified event to project_dir/actions.jsonl."""
    payload = FindingVerified(
        req=str(finding.get("req", "")),
        file=str(finding.get("file", "")),
        line=int(finding.get("line", 0)),
        note=finding.get("note"),
    )
    ActionLogWriter(project_dir).emit(FindingVerifiedEvent(payload=payload))


def unverify_finding(project_dir: Path, finding: dict) -> None:
    """Append a FindingUnverified event to project_dir/actions.jsonl."""
    payload = FindingUnverified(
        req=str(finding.get("req", "")),
        file=str(finding.get("file", "")),
        line=int(finding.get("line", 0)),
    )
    ActionLogWriter(project_dir).emit(FindingUnverifiedEvent(payload=payload))


def verified_entries(project_dir: Path) -> list[dict]:
    """Net verified badges: replay of VERIFIED/UNVERIFIED events in order."""
    if not project_dir.is_dir():
        return []
    entries: dict[tuple, dict] = {}
    for event in read_action_events(project_dir):
        if event.event_type == EventType.FINDING_VERIFIED:
            p = event.payload
            key = (str(p.req or ""), str(p.file or ""), int(p.line or 0))
            entries[key] = {
                "req": key[0], "file": key[1], "line": key[2],
                # note is always a string in entries; absent notes normalize
                # to "" so JSON and UI consumers never see null.
                "note": p.note or "",
                "verifiedAt": event.timestamp.isoformat(),
            }
        elif event.event_type == EventType.FINDING_UNVERIFIED:
            p = event.payload
            entries.pop((str(p.req or ""), str(p.file or ""), int(p.line or 0)), None)
    return list(entries.values())
