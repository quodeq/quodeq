"""A principle whose every violation is dismissed reads Insufficient in the CLI engine.

``_apply_suppressions`` keeps the emptied principle in the evidence, so the
engine scores a principle with no violations and no compliance. It must read
Insufficient (no score) like the projector and the legacy rescore, never 10.
"""
from __future__ import annotations

from quodeq.core.scoring.constants import Grade
from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services.evidence_rescore import EvidenceScoreRequest, score_dimension_from_evidence

from tests.services.test_evidence_rescore import DIM, _line, _write_evidence


def test_dimension_with_every_violation_dismissed_reads_insufficient(tmp_path):
    _write_evidence(tmp_path, [_line("R-1", "a.kt", 10), _line("R-2", "b.kt", 20, sev="critical")])
    out = score_dimension_from_evidence(
        tmp_path, DIM, EvidenceScoreRequest(
            dismissed={("R-1", "a.kt", 10), ("R-2", "b.kt", 20)}, deleted=set(),
            source_file_count=10, files_read=5, params=DEFAULT_PARAMS))
    assert out is not None
    emptied = out.principles["Modularity"]
    assert emptied.final_score is None and emptied.grade == Grade.INSUFFICIENT
    assert emptied.observation == 0.0
    assert out.overall.grade == Grade.INSUFFICIENT
    assert out.overall.weighted_score != 10.0
