"""Mapper functions for report, evidence, and principle-grade dataclasses."""

from __future__ import annotations

from .evidence import EvidenceFileMeta
from .finding import Totals
from .report import ParsedReport, PrincipleGrade

from ._mapper_helpers import _opt_int, _opt_str
from ._mapper_findings import _parse_finding_list, parse_totals


def _extract_totals(raw: dict[str, object]) -> Totals | None:
    """Parse a 'totals' field that may be a Totals instance, a raw dict, or absent."""
    totals_raw = raw.get("totals")
    if isinstance(totals_raw, Totals):
        return totals_raw
    if isinstance(totals_raw, dict):
        return parse_totals(totals_raw)
    return None


def parse_principle_grade(raw: dict[str, object]) -> PrincipleGrade:
    return PrincipleGrade(
        principle=_opt_str(raw.get("name")) or _opt_str(raw.get("principle")),
        score=_opt_str(raw.get("score")),
        grade=_opt_str(raw.get("grade")),
    )


def parse_parsed_report(raw: dict[str, object]) -> ParsedReport:
    principles_raw = raw.get("principles")
    principles: list[PrincipleGrade] = []
    if isinstance(principles_raw, list):
        principles = [parse_principle_grade(p) for p in principles_raw if isinstance(p, dict)]

    violations = _parse_finding_list(raw.get("violations"))
    compliance = _parse_finding_list(raw.get("compliance"))

    detail_raw = raw.get("detailPrinciples")
    detail_principles: list[dict[str, object]] = []
    if isinstance(detail_raw, list):
        detail_principles = list(detail_raw)

    totals = _extract_totals(raw)

    return ParsedReport(
        dimension=_opt_str(raw.get("dimension")),
        overall_score=_opt_str(raw.get("overallScore")),
        overall_grade=_opt_str(raw.get("overallGrade")),
        principles=principles,
        detail_principles=detail_principles,
        violations=violations,
        compliance=compliance,
        totals=totals,
    )


def parse_evidence_file_meta(raw: dict[str, object]) -> EvidenceFileMeta:
    dim = raw.get("dimension")
    if not isinstance(dim, str):
        msg = f"EvidenceFileMeta.dimension must be str, got {type(dim).__name__}"
        raise TypeError(msg)
    return EvidenceFileMeta(
        dimension=dim,
        source_file_count=_opt_int(raw.get("sourceFileCount")),
        date=_opt_str(raw.get("date")),
        discipline=_opt_str(raw.get("discipline")),
    )
