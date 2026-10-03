"""Wire shapes of the dashboard trend: the rows the history chart reads.

Declared here, away from the service that fills them, so the accumulation
logic depends on a contract rather than on the response format.
"""
from __future__ import annotations

from typing import TypedDict


class RunInfoPayload(TypedDict):
    """A run's identity on the wire: id plus its ISO and display dates.

    Every response that names a run (``availableRuns``, ``selectedRun``,
    ``trend``) carries these three keys, in this order.
    """
    runId: str
    dateISO: str | None
    dateLabel: str


class DimensionDetail(TypedDict):
    """One dimension's score/grade/delta within a single run's trend entry.

    Wire shape of ``trend[].dimensionDetails``; the keys are the contract
    the UI reads.
    """
    dimension: str
    score: float | None
    grade: str | None
    delta: float | None
    violations: int
    majors: int
    openTypes: int
    critical: int


class TrendEntry(TypedDict):
    """One run's accumulated-trend row, in the shape the dashboard HTTP
    response and the UI's history chart consume.

    Wire shape of ``trend``; the keys are the contract the UI reads.
    """
    runId: str
    dateISO: str | None
    dateLabel: str
    status: str
    dimensionsCount: int
    dimensions: list[str]
    dimensionDetails: list[DimensionDetail]
    accumulatedDimensionsCount: int
    runNumericAverage: float | None
    runOverallGrade: str | None
    numericAverage: float | None
    overallGrade: str | None
    violations: int
    majors: int
    openTypes: int
    critical: int
