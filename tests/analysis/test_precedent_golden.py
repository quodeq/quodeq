"""Threshold-sweep logic for the golden-set calibration script."""
from precedent_golden import sweep


def test_sweep_counts_tp_fp_fn() -> None:
    # d1 dismissed; p1 paraphrases d1; n1 unrelated.
    records = [
        {"id": "d1", "kind": "dismissal", "req": "R1", "snippet": "a"},
        {"id": "p1", "kind": "paraphrase", "of": "d1", "req": "R1", "snippet": "a'"},
        {"id": "n1", "kind": "negative", "req": "R9", "snippet": "z"},
    ]
    # Hand-crafted vectors: p1 close to d1 (cos ~0.98), n1 orthogonal.
    vectors = {
        "d1": [1.0, 0.0],
        "p1": [0.98, 0.2],
        "n1": [0.0, 1.0],
    }
    rows = sweep(records, lambda rec: vectors[rec["id"]], thresholds=[0.5, 0.99])
    by_thr = {row["threshold"]: row for row in rows}
    assert by_thr[0.5] == {"threshold": 0.5, "tp": 1, "fp": 0, "fn": 0,
                           "precision": 1.0, "recall": 1.0}
    assert by_thr[0.99]["tp"] == 0 and by_thr[0.99]["fn"] == 1
