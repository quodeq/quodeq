"""The severity classes in an evidence rescore request reach the scoring engine."""
from __future__ import annotations

import pytest

from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services.evidence_rescore import EvidenceScoreRequest, score_dimension_from_evidence

from tests.services.test_evidence_rescore import DIM, _line, _write_evidence


@pytest.fixture
def run_dir(tmp_path):
    _write_evidence(tmp_path, [
        _line("R-1", "a.kt", 10),
        _line("R-2", "a.kt", 20, sev="critical", vt="VT-GODCLASS"),
        _line("R-4", "c.kt", 9, p="Reusability"),
        _line("C-1", "a.kt", 1, t="compliance"),
    ])
    return tmp_path


def _score(run_dir, classes):
    out = score_dimension_from_evidence(
        run_dir, DIM, EvidenceScoreRequest(
            dismissed=set(), deleted=set(), source_file_count=10, files_read=5,
            params=DEFAULT_PARAMS, classes=classes))
    return out.overall.weighted_score


def test_classes_in_the_request_lower_the_rescored_score(run_dir):
    assert _score(run_dir, {"R-1": "critical", "R-2": "critical", "R-4": "critical"}) < _score(run_dir, {})
