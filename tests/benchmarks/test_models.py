import json
from pathlib import Path

import pytest

from quodeq_bench.models import CaseTruth, TruthError, load_truth

_VALID = {
    "language": "python",
    "exhaustive": True,
    "clean_files": ["storage.py"],
    "labels": [
        {
            "file": "app.py",
            "line": 13,
            "anchor": 'f"SELECT',
            "dimension": "security",
            "cwes": [89, 564],
            "reqs": [],
            "severity": "critical",
            "note": "f-string SQL",
        }
    ],
}


def _write_case(tmp_path: Path, payload: dict) -> Path:
    case = tmp_path / "py-sec-basic"
    case.mkdir()
    (case / "truth.json").write_text(json.dumps(payload), encoding="utf-8")
    return case


def test_load_valid_truth(tmp_path: Path) -> None:
    truth = load_truth(_write_case(tmp_path, _VALID))
    assert isinstance(truth, CaseTruth)
    assert truth.case_id == "py-sec-basic"
    assert truth.exhaustive is True
    assert truth.labels[0].cwes == (89, 564)
    assert truth.labels[0].dimension == "security"


def test_rejects_unknown_dimension(tmp_path: Path) -> None:
    bad = json.loads(json.dumps(_VALID))
    bad["labels"][0]["dimension"] = "velocity"
    with pytest.raises(TruthError, match="dimension"):
        load_truth(_write_case(tmp_path, bad))


def test_rejects_label_without_class(tmp_path: Path) -> None:
    bad = json.loads(json.dumps(_VALID))
    bad["labels"][0]["cwes"] = []
    bad["labels"][0]["reqs"] = []
    with pytest.raises(TruthError, match="cwes"):
        load_truth(_write_case(tmp_path, bad))


def test_rejects_nonpositive_line(tmp_path: Path) -> None:
    bad = json.loads(json.dumps(_VALID))
    bad["labels"][0]["line"] = 0
    with pytest.raises(TruthError, match="line"):
        load_truth(_write_case(tmp_path, bad))
