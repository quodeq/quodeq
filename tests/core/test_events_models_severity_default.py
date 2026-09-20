"""Judgment.severity's default ("medium") is defined once, on core.events.models
(DEFAULT_SEVERITY, alongside the existing VERDICT_VIOLATION/VERDICT_COMPLIANCE
pair), and every module that builds or reads a Judgment/Finding with a
fallback severity imports it rather than retyping "medium"."""
from __future__ import annotations

from quodeq.core.events.models import DEFAULT_SEVERITY, VERDICT_VIOLATION


def test_default_severity_is_medium():
    assert DEFAULT_SEVERITY == "medium"


def test_finding_mappings_uses_the_shared_default():
    from quodeq.core import finding_mappings

    assert finding_mappings.DEFAULT_SEVERITY is DEFAULT_SEVERITY


def test_req_mapping_uses_the_shared_default():
    from quodeq.core.evidence import _req_mapping

    assert _req_mapping.DEFAULT_SEVERITY is DEFAULT_SEVERITY


def test_evidence_parser_uses_the_shared_default():
    from quodeq.core.evidence import parser

    assert parser.DEFAULT_SEVERITY is DEFAULT_SEVERITY


def test_jsonl_parser_uses_the_shared_default():
    from quodeq.core.evidence import _jsonl

    assert _jsonl.DEFAULT_SEVERITY is DEFAULT_SEVERITY


def test_sqlite_row_mappers_use_the_shared_default_and_verdict():
    from quodeq.data.sqlite import _row_mappers

    assert _row_mappers.DEFAULT_SEVERITY is DEFAULT_SEVERITY
    assert _row_mappers.VERDICT_VIOLATION is VERDICT_VIOLATION
