from __future__ import annotations

from datetime import datetime
from typing import Optional, Protocol

from quodeq.core.events.models import JudgmentPayload


class StateStore(Protocol):
    """Write interface for the projection layer."""

    def apply_judgment(self, payload: JudgmentPayload) -> None:
        """Persist a judgment event into the state store."""
        ...

    def clear_all(self) -> None:
        """Wipe all projected state. Used before a full rebuild."""
        ...

    def get_checkpoint(self) -> Optional[datetime]:
        """Return the timestamp of the last successfully projected event."""
        ...

    def save_checkpoint(self, ts: datetime) -> None:
        """Persist the projection checkpoint."""
        ...
