from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Generic, List, Optional, TypeVar
from uuid import uuid4, UUID

from quodeq.core.types.req_ref import ReqRef


T = TypeVar("T")


class EventType(str, Enum):
    RUN_STARTED = "RUN_STARTED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_ABORTED = "RUN_ABORTED"
    JUDGMENT_CREATED = "JUDGMENT_CREATED"
    DIMENSION_COMPLETED = "DIMENSION_COMPLETED"
    DIMENSION_FAILED = "DIMENSION_FAILED"
    FINDING_DISMISSED = "FINDING_DISMISSED"
    FINDING_UNDISMISSED = "FINDING_UNDISMISSED"
    FINDING_VERIFIED = "FINDING_VERIFIED"
    FINDING_UNVERIFIED = "FINDING_UNVERIFIED"


@dataclass(frozen=True, kw_only=True)
class BaseEvent(Generic[T]):
    """Base class for all events in the quodeq event log."""

    event_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: EventType
    payload: T


@dataclass(frozen=True, kw_only=True)
class Judgment:
    """What the LLM produced about a single piece of code.

    Immutable. The canonical type for findings in the Event Log. Verdict is
    "violation" or "compliance" -- "dismissed" is NOT a valid Judgment verdict;
    that's a derived view-only state on Finding.
    """

    # Required
    practice_id: str
    verdict: str  # "violation" | "compliance"
    dimension: str
    file: str
    line: int
    reason: str

    # Optional
    end_line: Optional[int] = None
    snippet: Optional[str] = None
    severity: str = "medium"
    violation_type: Optional[str] = None
    title: Optional[str] = None
    context: Optional[str] = None
    scope: Optional[str] = None
    confidence: int = 100
    req: Optional[str] = None
    req_refs: List[ReqRef] = field(default_factory=list)
    cwe: Optional[str] = None
    # True when the deterministic provenance gate (#639) de-escalated this
    # finding from critical to major. UI/DB-visible audit marker (#656); the
    # severity flip already drives the grade, this just makes it auditable.
    provenance_downgrade: bool = False
    # Set (dict: {"rule", "from", "to"}) when the deterministic scope gate
    # capped this finding's severity from major to minor per the declared
    # trust model. None when not gated. A dict, not a bool, because the
    # marker's whole purpose is naming WHICH rule waived the finding so it
    # can be recovered later, not just that something did.
    scope_downgrade: Optional[Dict[str, str]] = None
    # True when this finding was replayed from the content-addressed cache
    # rather than produced by the running scan. Lets the live evaluation
    # feed show only what this scan is actually finding (the rest of the
    # app still shows every finding in the run).
    carried_forward: bool = False

    def is_violation(self) -> bool:
        return self.verdict == "violation"

    def is_compliance(self) -> bool:
        return self.verdict == "compliance"


# Deprecation alias -- remove in a follow-up PR once all callers migrate.
JudgmentPayload = Judgment


@dataclass(frozen=True, kw_only=True)
class JudgmentCreatedEvent(BaseEvent[Judgment]):
    """Event emitted whenever a new judgment is found and recorded."""

    event_type: EventType = EventType.JUDGMENT_CREATED


@dataclass(frozen=True, kw_only=True)
class FindingDismissed:
    """User dismissed a finding identified by (req, file, line)."""

    req: str
    file: str
    line: int
    reason: Optional[str] = None


@dataclass(frozen=True, kw_only=True)
class FindingUndismissed:
    """User restored a previously dismissed finding."""

    req: str
    file: str
    line: int


@dataclass(frozen=True, kw_only=True)
class FindingDismissedEvent(BaseEvent[FindingDismissed]):
    event_type: EventType = EventType.FINDING_DISMISSED


@dataclass(frozen=True, kw_only=True)
class FindingUndismissedEvent(BaseEvent[FindingUndismissed]):
    event_type: EventType = EventType.FINDING_UNDISMISSED


@dataclass(frozen=True, kw_only=True)
class FindingVerified:
    """User confirmed a finding is a real defect, identified by (req, file, line)."""

    req: str
    file: str
    line: int
    note: Optional[str] = None


@dataclass(frozen=True, kw_only=True)
class FindingUnverified:
    """User cleared a previously verified badge."""

    req: str
    file: str
    line: int


@dataclass(frozen=True, kw_only=True)
class FindingVerifiedEvent(BaseEvent[FindingVerified]):
    event_type: EventType = EventType.FINDING_VERIFIED


@dataclass(frozen=True, kw_only=True)
class FindingUnverifiedEvent(BaseEvent[FindingUnverified]):
    event_type: EventType = EventType.FINDING_UNVERIFIED


# Mapping to allow the Reader to resolve the correct model for validation
# This is crucial for correct payload parsing
EVENT_MODEL_MAP: Dict[EventType, type[BaseEvent]] = {
    EventType.JUDGMENT_CREATED: JudgmentCreatedEvent,
    EventType.FINDING_DISMISSED: FindingDismissedEvent,
    EventType.FINDING_UNDISMISSED: FindingUndismissedEvent,
    EventType.FINDING_VERIFIED: FindingVerifiedEvent,
    EventType.FINDING_UNVERIFIED: FindingUnverifiedEvent,
}

# Payload class per event type. The decoder (data.events.codec) uses it to
# construct the nested payload dataclass for each event model.
PAYLOAD_MODEL_MAP: Dict[EventType, type] = {
    EventType.JUDGMENT_CREATED: Judgment,
    EventType.FINDING_DISMISSED: FindingDismissed,
    EventType.FINDING_UNDISMISSED: FindingUndismissed,
    EventType.FINDING_VERIFIED: FindingVerified,
    EventType.FINDING_UNVERIFIED: FindingUnverified,
}
