from quodeq.config.coverage import parse_coverage_percent


def test_parse_coverage_percent():
    assert parse_coverage_percent("75%") == 75
