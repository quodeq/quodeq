from __future__ import annotations

from codecompass.evaluate.lib.scoring import run_scoring as v1_run_scoring
from codecompass.v2.engine.evidence import Evidence


def score_evidence(evidence: Evidence, mode: str = "numerical") -> dict:
    """Score v2 Evidence using v1's proven scoring engine.

    Converts Evidence to the v1 dict shape and delegates to run_scoring().
    """
    v1_dict = evidence.to_v1_evidence_dict()
    return v1_run_scoring(v1_dict, mapping={}, mode=mode)
