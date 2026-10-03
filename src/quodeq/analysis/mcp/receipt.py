"""What the router tells a writer about one reported finding."""
from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple


class ReceiptStatus(StrEnum):
    """The outcome of reporting one finding."""

    RECORDED = "recorded"      # placed in its standard and written
    DUPLICATE = "duplicate"    # already captured; nothing written
    REJECTED = "rejected"      # unknown requirement, first attempt: the model is asked to retry
    UNMAPPED = "unmapped"      # unknown requirement again: written as unmapped, never graded


class Receipt(NamedTuple):
    """The message for the model and the outcome behind it."""

    message: str
    status: ReceiptStatus

    @property
    def is_error(self) -> bool:
        """True when the tool call should be reported to the model as failed."""
        return self.status is ReceiptStatus.REJECTED
