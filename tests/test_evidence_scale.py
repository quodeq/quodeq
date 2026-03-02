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
