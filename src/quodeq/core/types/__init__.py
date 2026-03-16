from __future__ import annotations

from ._serialization import to_camel_dict
from .dashboard import AccumulatedSummary, DashboardSummary, TrendPoint
from .dimension import DimensionResult, DimensionSummary, GradeBreakdown
from .evidence import EvidenceFileMeta
from .finding import Finding, ReqRef, SeverityTally, Totals
from .job import JobSnapshot
from .json import JsonObject, JsonValue
from .plugin import PluginDimension, PluginInfo
from .project import ProjectEntry, ProjectMetadata
from .report import ParsedReport, PrincipleGrade, PrincipleGradeWithOverall
from .scoring import Deductions, OverallScore, PrincipleScore, ScaleInfo, ScoringResult
from .violation import ProgressInfo, ViolationFileEntry, ViolationResponse, ViolationSummary

__all__ = [
    "AccumulatedSummary",
    "DashboardSummary",
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
    "TrendPoint",
    "ViolationFileEntry",
    "ViolationResponse",
    "ViolationSummary",
    "to_camel_dict",
]
