"""The rescore request carries no severity-class override: the grade follows the finding's severity."""
from quodeq.services.evidence_rescore import EvidenceScoreRequest


def test_request_has_no_classes_field():
    assert "classes" not in EvidenceScoreRequest.__dataclass_fields__
