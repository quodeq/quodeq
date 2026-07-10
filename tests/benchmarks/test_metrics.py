from pathlib import Path

from quodeq_bench.matcher import CaseMatch
from quodeq_bench.metrics import DimensionMetrics, aggregate, count_kloc


def test_aggregate_two_cases() -> None:
    case_a = {
        "security": CaseMatch(
            total_labels=2, matched_labels=1, matched_findings=2,
            fp_findings=1, duplicates=1, severity_agreements=1,
        )
    }
    case_b = {
        "security": CaseMatch(
            total_labels=2, matched_labels=2, matched_findings=2,
            fp_findings=0, duplicates=0, severity_agreements=2,
        )
    }
    metrics = aggregate([case_a, case_b], [1.0, 1.0])
    sec = metrics["security"]
    assert sec.total_labels == 4
    assert sec.matched_labels == 3
    assert sec.recall == 0.75
    assert sec.precision == 4 / 5
    assert sec.kloc == 2.0
    assert sec.fp_density == 0.5


def test_zero_denominators_are_zero() -> None:
    empty = DimensionMetrics()
    assert empty.precision == 0.0
    assert empty.recall == 0.0
    assert empty.f1 == 0.0


def test_as_dict_round_numbers() -> None:
    m = DimensionMetrics(total_labels=3, matched_labels=1)
    d = m.as_dict()
    assert d["recall"] == round(1 / 3, 4)
    assert d["total_labels"] == 3


def test_count_kloc(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n\ny = 2\n", encoding="utf-8")
    (tmp_path / "truth.json").write_text("{}", encoding="utf-8")
    assert count_kloc(tmp_path, "python") == 0.002
