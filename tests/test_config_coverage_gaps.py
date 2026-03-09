from quodeq.config.coverage import coverage_percent


def test_coverage_percent_parses_fraction():
    assert coverage_percent("3/10") == 30
