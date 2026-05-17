from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar, Union
from uuid import uuid4, UUID

from pydantic import BaseModel, Field, ConfigDict

from quodeq.core.types.req_ref import ReqRef


T = TypeVar("T")


class EventType(str, Enum):
    RUN_STARTED = "RUN_STARTED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_ABORTED = "RUN_ABORTED"
    JUDGMENT_CREATED = "JUDGMENT_CREATED"
    DIMENSION_COMPLETED = "DIMENSION_COMPLETED"
    DIMENSION_FAILED = "DIMENSION_FAILED"


class BaseEvent(BaseModel, Generic[T]):
    """Base class for all events in the quodeq event log."""
    model_config = ConfigDict(frozen=True)

    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: EventType
    payload: T


class Judgment(BaseModel):
    """What the LLM produced about a single piece of code.

    Immutable. The canonical type for findings in the Event Log. Verdict is
    "violation" or "compliance" -- "dismissed" is NOT a valid Judgment verdict;
    that's a derived view-only state on Finding.
    """
    model_config = ConfigDict(frozen=True)

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
    req_refs: List[ReqRef] = Field(default_factory=list)
    cwe: Optional[str] = None

    def is_violation(self) -> bool:
        return self.verdict == "violation"

    def is_compliance(self) -> bool:
        return self.verdict == "compliance"


# Deprecation alias -- remove in a follow-up PR once all callers migrate.
JudgmentPayload = Judgment


class JudgmentCreatedEvent(BaseEvent[Judgment]):
    """Event emitted whenever a new judgment is found and recorded."""
    event_type: EventType = EventType.JUDGMENT_CREATED


# Mapping to allow the Reader to resolve the correct model for validation
# This is crucial for correct payload parsing
EVENT_MODEL_MAP: Dict[EventType, type[BaseEvent]] = {
    EventType.JUDGMENT_CREATED: JudgmentCreatedEvent,
}
