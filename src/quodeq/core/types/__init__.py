"""Domain value objects shared across layers; re-exports every per-topic module.

The split into ``finding``, ``scoring``, ``report`` and the rest is a
file-size boundary; ``__all__`` below is the public surface.
"""
from __future__ import annotations

from .dimension import DimensionResult, DimensionSummary, GradeBreakdown
from .evidence import EvidenceFileMeta
from .finding import Finding, ReqRef, SeverityTally, Totals
from .job import JobSnapshot
from .json import JsonObject, JsonValue
from .plugin import PluginDimension, PluginInfo
from .project import ProjectEntry, ProjectMetadata
from .report import ParsedReport, PrincipleGrade, PrincipleGradeWithOverall
from .scoring import ConfidenceLevel, Deductions, OverallScore, PrincipleScore, ScaleInfo, ScoringResult
from .violation import ProgressInfo, ViolationFileEntry, ViolationResponse, ViolationSummary

__all__ = [
    "ConfidenceLevel",
    "Deductions",
    "DimensionResult",
    "DimensionSummary",
    "EvidenceFileMeta",
    "Finding",
    "GradeBreakdown",
    "JobSnapshot",
    "JsonObject",
    "JsonValue",
    "OverallScore",
    "ParsedReport",
    "PluginDimension",
    "PluginInfo",
    "PrincipleGrade",
    "PrincipleGradeWithOverall",
    "PrincipleScore",
    "ProgressInfo",
    "ProjectEntry",
    "ProjectMetadata",
    "ReqRef",
    "ScaleInfo",
    "ScoringResult",
    "SeverityTally",
    "Totals",
    "ViolationFileEntry",
    "ViolationResponse",
    "ViolationSummary",
]
