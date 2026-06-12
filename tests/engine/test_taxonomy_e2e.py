"""End-to-end regression: a 'vt' taxonomy survives parse -> score.

Guards the seam between judgment_to_dict (writer) and the scoring tally
(reader). The unit tests in test_scoring.py hand-build violation dicts with
the 'vt' key, so they cannot catch a writer/reader key drift on the real
production path; this test drives the actual parser.
"""
from __future__ import annotations

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
