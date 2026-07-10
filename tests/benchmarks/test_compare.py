from quodeq_bench.compare import Regression, compare_reports


def _report(precision: float, recall: float) -> dict:
    return {
        "meta": {},
        "errored": False,
        "metrics": {"security": {"precision": precision, "recall": recall}},
    }


def test_no_regression_within_threshold() -> None:
    assert compare_reports(_report(0.8, 0.8), _report(0.76, 0.79)) == []


def test_regression_beyond_threshold() -> None:
    result = compare_reports(_report(0.8, 0.8), _report(0.7, 0.8))
    assert result == [
        Regression(dimension="security", metric="precision", baseline=0.8, candidate=0.7)
    ]


def test_missing_dimension_is_regression() -> None:
    candidate = {"meta": {}, "errored": False, "metrics": {}}
    result = compare_reports(_report(0.8, 0.8), candidate)
    assert {r.metric for r in result} == {"precision", "recall"}


def test_bootstrap_baseline_never_fails() -> None:
    baseline = {"bootstrap": True, "metrics": {}}
    assert compare_reports(baseline, _report(0.0, 0.0)) == []


def test_improvement_is_not_regression() -> None:
    assert compare_reports(_report(0.5, 0.5), _report(0.9, 0.9)) == []
