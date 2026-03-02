from codecompass.evaluate.lib.evidence import _compute_principle_metrics


def _make_bucket(n_violations, n_compliance):
    return {
        "violations": [{}] * n_violations,
        "compliance": [{}] * n_compliance,
    }


def test_confidence_level_scale_1_default():
    # scale=1: high >= 10, medium >= 5, low < 5
    p = {"a": _make_bucket(8, 2)}
    _compute_principle_metrics(p)
    assert p["a"]["metrics"]["confidence_level"] == "high"   # 10 >= 10

    p = {"a": _make_bucket(3, 2)}
    _compute_principle_metrics(p)
    assert p["a"]["metrics"]["confidence_level"] == "medium"  # 5 >= 5

    p = {"a": _make_bucket(2, 1)}
    _compute_principle_metrics(p)
    assert p["a"]["metrics"]["confidence_level"] == "low"    # 3 < 5


def test_confidence_level_scale_4():
    # scale=4: high >= 40, medium >= 20, low < 20
    p = {"a": _make_bucket(25, 15)}  # 40 total
    _compute_principle_metrics(p, scale_multiplier=4)
    assert p["a"]["metrics"]["confidence_level"] == "high"

    p = {"a": _make_bucket(15, 5)}  # 20 total
    _compute_principle_metrics(p, scale_multiplier=4)
    assert p["a"]["metrics"]["confidence_level"] == "medium"

    p = {"a": _make_bucket(8, 2)}  # 10 total, would be 'high' at scale=1
    _compute_principle_metrics(p, scale_multiplier=4)
    assert p["a"]["metrics"]["confidence_level"] == "low"   # 10 < 20


import json
import tempfile
from pathlib import Path

from codecompass.evaluate.lib.evidence import assemble_evidence_from_jsonl


def test_assemble_evidence_stores_files_read_and_coverage():
    """files_read and coverage_pct are written into the evidence JSON."""
    finding = '{"p": "key1", "t": "violation", "file": "a.py", "severity": "minor", "reason": "r"}\n'
    with tempfile.TemporaryDirectory() as tmp:
        jsonl = Path(tmp) / "findings.jsonl"
        output = Path(tmp) / "evidence.json"
        jsonl.write_text(finding)

        assemble_evidence_from_jsonl(
            jsonl_file=str(jsonl),
            output_file=str(output),
            repo_name="testrepo",
            discipline="python",
            date_str="2026-01-01",
            source_file_count=1000,
            files_read=50,
        )

        evidence = json.loads(output.read_text())
        assert evidence["files_read"] == 50
        assert evidence["coverage_pct"] == 5.0   # 50/1000 * 100
