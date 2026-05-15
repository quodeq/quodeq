from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar, Union
from uuid import uuid4, UUID

from pydantic import BaseModel, Field, ConfigDict


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


class JudgmentPayload(BaseModel):
    """Payload for JUDGMENT_CREATED event, expanded from the legacy JSONL structure."""
    model_config = ConfigDict(frozen=True)

    practice_id: str
    verdict: str  # "violation" | "compliance"
    dimension: str
    file: str
    line: int
    end_line: Optional[int] = None
    snippet: Optional[str] = None
    severity: str = "medium"
    violation_type: Optional[str] = None
    reason: str
    title: Optional[str] = None
    context: Optional[str] = None
    scope: Optional[str] = None
    confidence: int = 100
    req_refs: List[str] = Field(default_factory=list)
    req: Optional[str] = None
    cwe: Optional[str] = None


class JudgmentCreatedEvent(BaseEvent[JudgmentPayload]):
    """Event emitted whenever a new judgment is found and recorded."""
    event_type: EventType = EventType.JUDGMENT_CREATED


# Mapping to allow the Reader to resolve the correct model for validation
# This is crucial for correct payload parsing
EVENT_MODEL_MAP: Dict[EventType, type[BaseEvent]] = {
    EventType.JUDGMENT_CREATED: JudgmentCreatedEvent,
}
