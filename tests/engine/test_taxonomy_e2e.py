"""End-to-end regression: a 'vt' taxonomy survives parse -> score.

Guards the seam between judgment_to_dict (writer) and the scoring tally
(reader). The unit tests in test_scoring.py hand-build violation dicts with
the 'vt' key, so they cannot catch a writer/reader key drift on the real
production path; this test drives the actual parser.
"""
from __future__ import annotations

import json

import pytest

from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.core.scoring.engine import score_evidence

from tests.engine.conftest import _evidence_line


def test_taxonomy_used_on_parse_then_score(tmp_path):
    jsonl = tmp_path / "evidence.jsonl"
    jsonl.write_text("\n".join([
        _evidence_line(p="ts-001", t="violation", vt="code-injection",
                       severity="critical", file="src/a.ts", line=1),
        _evidence_line(p="ts-001", t="violation", vt="code-injection",
                       severity="critical", file="src/b.ts", line=2),
        _evidence_line(p="ts-001", t="violation", vt="code-injection",
                       severity="critical", file="src/c.ts", line=3),
    ]) + "\n")

    evidence = parse_jsonl_to_evidence(
        jsonl,
        EvidenceContext(language="typescript", repository="test-repo",
                        date_str="2026-06-12", source_file_count=50, files_read=10),
    )
    scores = score_evidence(evidence, mode="numerical")

    principle = scores.principles["ts-001"]
    assert principle.taxonomy_used is True


def test_taxonomy_from_mcp_producer_to_score(tmp_path):
    """A fresh MCP/CLI-path run whose report_finding calls carry 'vt' must
    score with taxonomy_used=True.

    Drives the genuine MCP producer seam: the agent's report_finding
    arguments are forwarded verbatim by handle_tools_call to
    FindingsRouter.receive, which delegates to FindingEnricher.enrich (the
    enricher copies every non-None arg key, including 'vt', into the JSONL
    line) before the real parse -> score. Before the schema documented 'vt',
    the default per-dimension template never instructed the model to emit it,
    so fresh runs fell back to free-text reason grouping.
    """
    from quodeq.analysis.mcp.router import FindingsRouter

    # Exactly the shape handle_tools_call forwards (params['arguments']) for a
    # report_finding MCP tool call: three near-duplicate findings sharing 'vt'.
    report_finding_args = [
        {"p": "ts-001", "t": "violation", "file": f"src/{name}.ts", "line": i,
         "severity": "critical", "w": "eval usage", "snippet": "eval(userInput)",
         "reason": reason, "vt": "code-injection"}
        for i, (name, reason) in enumerate([
            ("a", "eval of user input enables code injection."),
            ("b", "Dynamic eval executes attacker-controlled strings."),
            ("c", "Unsanitised input reaches eval."),
        ], start=1)
    ]

    jsonl = tmp_path / "evidence.jsonl"
    with open(jsonl, "w") as fh:
        router = FindingsRouter(fh)
        for args in report_finding_args:
            _message, is_dup = router.receive(args)
            assert is_dup is False

    evidence = parse_jsonl_to_evidence(
        jsonl,
        EvidenceContext(language="typescript", repository="test-repo",
                        date_str="2026-06-12", source_file_count=50, files_read=10),
    )
    scores = score_evidence(evidence, mode="numerical")

    principle = scores.principles["ts-001"]
    assert principle.taxonomy_used is True


def test_taxonomy_from_api_producer_to_score(tmp_path):
    """A fresh API-runner run whose model output carries 'vt' must score with
    taxonomy_used=True.

    Drives the actual producer seam the writer-side tests above cannot reach:
    raw model output -> _parse_findings (_Finding validation) -> FindingsRouter
    -> JSONL -> parse -> score. Before _Finding carried 'vt', validation
    silently stripped the taxonomy and every fresh run fell back to free-text
    reason grouping.
    """
    pytest.importorskip("openai", reason="requires the openai SDK")
    from quodeq.analysis._api_runner import _parse_findings
    from quodeq.analysis.mcp.router import FindingsRouter

    raw = json.dumps({"findings": [
        {"req": "ts-001", "t": "violation", "file": f"src/{name}.ts", "line": i,
         "severity": "critical", "w": "eval usage", "snippet": "eval(userInput)",
         "reason": reason, "vt": "code-injection"}
        for i, (name, reason) in enumerate([
            ("a", "eval of user input enables code injection."),
            ("b", "Dynamic eval executes attacker-controlled strings."),
            ("c", "Unsanitised input reaches eval."),
        ], start=1)
    ]})
    findings, dropped = _parse_findings(raw)
    assert dropped == 0
    assert len(findings) == 3

    jsonl = tmp_path / "evidence.jsonl"
    with open(jsonl, "w") as fh:
        router = FindingsRouter(fh)
        for f in findings:
            router.receive(f)

    evidence = parse_jsonl_to_evidence(
        jsonl,
        EvidenceContext(language="typescript", repository="test-repo",
                        date_str="2026-06-12", source_file_count=50, files_read=10),
    )
    scores = score_evidence(evidence, mode="numerical")

    principle = scores.principles["ts-001"]
    assert principle.taxonomy_used is True
