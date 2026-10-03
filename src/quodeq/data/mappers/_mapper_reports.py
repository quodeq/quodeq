"""Mapper functions for report, evidence, and principle-grade dataclasses."""

from __future__ import annotations

from quodeq.core.types.evidence import EvidenceFileMeta
from quodeq.core.types.finding import Totals
from quodeq.core.types.report import ParsedReport, PrincipleGrade

from ._mapper_helpers import get_opt_int, get_opt_str
from ._mapper_findings import parse_finding_list, parse_totals


def extract_totals(raw: dict[str, object]) -> Totals | None:
    """Parse a 'totals' field that may be a Totals instance, a raw dict, or absent."""
    totals_raw = raw.get("totals")
    if isinstance(totals_raw, Totals):
        return totals_raw
    if isinstance(totals_raw, dict):
        return parse_totals(totals_raw)
    return None


def parse_principle_grade(raw: dict[str, object]) -> PrincipleGrade:
    """Parse a raw dict into a PrincipleGrade dataclass."""
    return PrincipleGrade(
        principle=get_opt_str(raw.get("name")) or get_opt_str(raw.get("principle")),
        score=get_opt_str(raw.get("score")),
        grade=get_opt_str(raw.get("grade")),
    )


def parse_principle_grades(raw: dict[str, object]) -> list[PrincipleGrade]:
    """Parse the ``principles`` field of *raw*; empty when absent or not a list of dicts."""
    principles_raw = raw.get("principles")
    if not isinstance(principles_raw, list):
        return []
    return [parse_principle_grade(p) for p in principles_raw if isinstance(p, dict)]


def parse_parsed_report(raw: dict[str, object]) -> ParsedReport:
    """Parse a raw dict into a ParsedReport dataclass."""
    principles = parse_principle_grades(raw)

    violations = parse_finding_list(raw.get("violations"))
    compliance = parse_finding_list(raw.get("compliance"))

    detail_raw = raw.get("detailPrinciples")
    detail_principles: list[dict[str, object]] = []
    if isinstance(detail_raw, list):
        detail_principles = list(detail_raw)

    totals = extract_totals(raw)

    return ParsedReport(
        dimension=get_opt_str(raw.get("dimension")),
        overall_score=get_opt_str(raw.get("overallScore")),
        overall_grade=get_opt_str(raw.get("overallGrade")),
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
        source_file_count=get_opt_int(raw.get("sourceFileCount")),
        date=get_opt_str(raw.get("date")),
        discipline=get_opt_str(raw.get("discipline")),
    )
