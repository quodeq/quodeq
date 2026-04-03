"""Incremental analysis — detect changes, classify files, carry forward findings.

This module re-exports all public symbols from the split sub-modules and
contains the file-classification orchestration logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from quodeq.analysis._incr_change_detection import (
    ChangeDetectionResult,
    detect_changed_files,
)
from quodeq.analysis._incr_dependency import find_dependents
from quodeq.analysis._incr_carry_forward import carry_forward_findings

# Re-export everything that external callers import from this module.
__all__ = [
    "ChangeDetectionResult",
    "detect_changed_files",
    "find_dependents",
    "carry_forward_findings",
    "FileClassification",
    "ClassificationInput",
    "classify_files",
    "identify_backfill_files",
]

from pathlib import Path


@dataclass
class FileClassification:
    """Classified files for incremental analysis."""
    to_analyze: list[str] = field(default_factory=list)
    unchanged: set[str] = field(default_factory=set)
    full_reanalysis: bool = False


@dataclass
class ClassificationInput:
    """Grouped inputs for file classification."""
    src: Path
    files: list[str]
    prev_fingerprint: dict | None
    standards_dir: Path | None
    dimension: str
    language: str


def classify_files(*, inputs: "ClassificationInput") -> FileClassification:
    """Classify files into to_analyze (changed + dependents) and unchanged."""
    detection = detect_changed_files(inputs.src, inputs.files, inputs.prev_fingerprint, inputs.standards_dir, inputs.dimension)
    if detection.full_reanalysis:
        return FileClassification(to_analyze=list(inputs.files), full_reanalysis=True)
    dependents = find_dependents(detection.changed, inputs.files, inputs.src, inputs.language)
    to_analyze = detection.changed | dependents
    unchanged = set(inputs.files) - to_analyze
    return FileClassification(to_analyze=sorted(to_analyze), unchanged=unchanged)


def identify_backfill_files(
    all_files: list[str],
    prev_analyzed: list[str],
    already_queued: set[str],
) -> list[str]:
    """Identify files never analyzed that aren't already queued for this run.

    Returns files in the same order as all_files (preserving priority ordering).
    """
    covered = set(prev_analyzed) | already_queued
    return [f for f in all_files if f not in covered]
